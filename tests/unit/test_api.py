import json
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore

import app.api.routers.chat as chat_module
import app.api.routers.research as research_module
from app.api.dependencies import (
    provide_application_repository,
    provide_evaluation_catalog_repository,
    provide_evaluation_run_repository,
    provide_review_repository,
    provide_reporting_repository,
    provide_gate_repository,
    provide_identity_repository,
    provide_jwt_settings,
    provide_memory_store,
    provide_workspace_repository,
)
from app.api.main import create_app
from app.api.rate_limit import (
    FixedWindowRateLimiter,
    RateLimitSettings,
)
from app.security import (
    InMemoryIdentityRepository,
    JWTSettings,
)
from app.applications import InMemoryApplicationRepository
from app.evaluation import InMemoryEvaluationCatalogRepository
from app.evaluation import InMemoryEvaluationRunRepository
from app.evaluation import InMemoryReviewRepository
from app.evaluation.reporting import InMemoryReportingRepository
from app.evaluation.gates import InMemoryGateRepository
from tests.unit.test_reporting import reporting_snapshot
from app.evaluation.reviews import ReviewCaseRecord, ReviewCriterionRecord
from app.tools.memory_tools import build_memory_namespace
from app.workspaces import InMemoryWorkspaceRepository


TEST_JWT_SETTINGS = JWTSettings(
    secret_key="unit-test-secret-key-with-more-than-32-characters",
    access_token_expire_minutes=5,
)


@pytest.fixture
def memory_store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def identity_repository() -> InMemoryIdentityRepository:
    return InMemoryIdentityRepository()


@pytest.fixture
def workspace_repository() -> InMemoryWorkspaceRepository:
    return InMemoryWorkspaceRepository()


@pytest.fixture
def application_repository(
    workspace_repository: InMemoryWorkspaceRepository,
) -> InMemoryApplicationRepository:
    return InMemoryApplicationRepository(workspace_repository)


@pytest.fixture
def evaluation_catalog_repository(
    workspace_repository: InMemoryWorkspaceRepository,
) -> InMemoryEvaluationCatalogRepository:
    return InMemoryEvaluationCatalogRepository(workspace_repository)


@pytest.fixture
def evaluation_run_repository() -> InMemoryEvaluationRunRepository:
    return InMemoryEvaluationRunRepository()


@pytest.fixture
def review_repository() -> InMemoryReviewRepository:
    return InMemoryReviewRepository()


@pytest.fixture
def reporting_repository() -> InMemoryReportingRepository:
    return InMemoryReportingRepository()


@pytest.fixture
def gate_repository() -> InMemoryGateRepository:
    return InMemoryGateRepository()


@pytest.fixture
def client(
    memory_store: InMemoryStore,
    identity_repository: InMemoryIdentityRepository,
    workspace_repository: InMemoryWorkspaceRepository,
    application_repository: InMemoryApplicationRepository,
    evaluation_catalog_repository: InMemoryEvaluationCatalogRepository,
    evaluation_run_repository: InMemoryEvaluationRunRepository,
    review_repository: InMemoryReviewRepository,
    reporting_repository: InMemoryReportingRepository,
    gate_repository: InMemoryGateRepository,
) -> Iterator[TestClient]:
    application = create_app(
        rate_limiter=FixedWindowRateLimiter(
            RateLimitSettings(requests=1000, window_seconds=60)
        )
    )
    application.dependency_overrides[
        provide_memory_store
    ] = lambda: memory_store
    application.dependency_overrides[
        provide_identity_repository
    ] = lambda: identity_repository
    application.dependency_overrides[
        provide_workspace_repository
    ] = lambda: workspace_repository
    application.dependency_overrides[
        provide_application_repository
    ] = lambda: application_repository
    application.dependency_overrides[
        provide_evaluation_catalog_repository
    ] = lambda: evaluation_catalog_repository
    application.dependency_overrides[
        provide_evaluation_run_repository
    ] = lambda: evaluation_run_repository
    application.dependency_overrides[
        provide_review_repository
    ] = lambda: review_repository
    application.dependency_overrides[
        provide_reporting_repository
    ] = lambda: reporting_repository
    application.dependency_overrides[
        provide_gate_repository
    ] = lambda: gate_repository
    application.dependency_overrides[
        provide_jwt_settings
    ] = lambda: TEST_JWT_SETTINGS

    with TestClient(application) as test_client:
        yield test_client


def register_and_login(
    client: TestClient,
    username: str = "bei",
    password: str = "secure-password",
) -> tuple[dict[str, str], dict]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert register_response.status_code == 201
    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    return (
        {"Authorization": f"Bearer {token}"},
        register_response.json(),
    )


def test_liveness_and_request_id(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "test-request-id"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "researchflow",
    }
    assert response.headers["X-Request-ID"] == "test-request-id"


def test_metrics_endpoint_exposes_researchflow_metrics(
    client: TestClient,
) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert (
        "researchflow_http_requests_total"
        in response.text
    )


def test_rate_limit_rejects_excess_requests() -> None:
    application = create_app(
        rate_limiter=FixedWindowRateLimiter(
            RateLimitSettings(
            requests=2,
            window_seconds=60,
            )
        ),
    )
    with TestClient(application) as test_client:
        first = test_client.post("/api/v1/chat", json={})
        second = test_client.post("/api/v1/chat", json={})
        rejected = test_client.post("/api/v1/chat", json={})

    assert first.status_code == 401
    assert second.status_code == 401
    assert rejected.status_code == 429
    assert rejected.headers["retry-after"]
    assert rejected.headers["x-ratelimit-remaining"] == "0"


def test_register_login_and_current_user(
    client: TestClient,
) -> None:
    headers, user = register_and_login(client)
    assert user["username"] == "bei"
    assert "password" not in user

    me_response = client.get(
        "/api/v1/auth/me",
        headers=headers,
    )
    assert me_response.status_code == 200
    assert me_response.json() == user

    duplicate_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "bei",
            "password": "another-password",
        },
    )
    assert duplicate_response.status_code == 409

    wrong_password_response = client.post(
        "/api/v1/auth/token",
        data={"username": "bei", "password": "wrong-password"},
    )
    assert wrong_password_response.status_code == 401


def test_refresh_token_rotates_and_logout_revokes(
    client: TestClient,
) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "refresh-user",
            "password": "secure-password",
        },
    )
    assert register_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "refresh-user",
            "password": "secure-password",
        },
    )
    old_refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert refresh_response.status_code == 200
    new_refresh_token = refresh_response.json()["refresh_token"]
    assert new_refresh_token != old_refresh_token

    replay_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert replay_response.status_code == 401

    logout_response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_refresh_token},
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"revoked": True}

    revoked_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert revoked_response.status_code == 401


def test_change_password_revokes_refresh_and_is_audited(
    client: TestClient,
) -> None:
    headers, _ = register_and_login(
        client,
        username="password-user",
        password="old-secure-password",
    )
    login = client.post(
        "/api/v1/auth/token",
        data={
            "username": "password-user",
            "password": "old-secure-password",
        },
    ).json()
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "old-secure-password",
            "new_password": "new-secure-password",
        },
    )
    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["revoked_refresh_sessions"] >= 1

    revoked = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert revoked.status_code == 401
    assert client.post(
        "/api/v1/auth/token",
        data={
            "username": "password-user",
            "password": "new-secure-password",
        },
    ).status_code == 200

    audit = client.get(
        "/api/v1/users/me/audit-events",
        headers=headers,
    )
    assert audit.status_code == 200
    event_types = {
        event["event_type"]
        for event in audit.json()["events"]
    }
    assert "auth.password_change" in event_types


def test_issue_mcp_token_is_resource_bound(
    client: TestClient,
) -> None:
    headers, _ = register_and_login(client, "mcp-user")
    response = client.post(
        "/api/v1/auth/mcp-token",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == "http://127.0.0.1:8001/mcp"
    assert "research:read" in body["scope"]


def test_protected_endpoint_requires_bearer_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"question": "RT-2是什么？"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_chat_endpoint_uses_authenticated_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, user = register_and_login(client)

    def fake_agent(
        question: str,
        user_id: str,
        thread_id: str,
    ) -> dict:
        assert question == "RT-2是什么？"
        assert user_id == user["user_id"]
        assert thread_id == "chat-thread"
        return {"messages": [AIMessage(content="测试Agent答案")]}

    monkeypatch.setattr(
        chat_module,
        "run_research_agent",
        fake_agent,
    )
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "question": "RT-2是什么？",
            "thread_id": "chat-thread",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "answer": "测试Agent答案",
        "user_id": user["user_id"],
        "thread_id": "chat-thread",
    }


def test_thread_ownership_blocks_other_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_headers, _ = register_and_login(client, "first-user")
    second_headers, _ = register_and_login(client, "second-user")
    monkeypatch.setattr(
        chat_module,
        "run_research_agent",
        lambda **kwargs: {
            "messages": [AIMessage(content="ok")]
        },
    )

    first = client.post(
        "/api/v1/chat",
        headers=first_headers,
        json={"question": "问题", "thread_id": "owned-thread"},
    )
    second = client.post(
        "/api/v1/chat",
        headers=second_headers,
        json={"question": "问题", "thread_id": "owned-thread"},
    )
    assert first.status_code == 200
    assert second.status_code == 403
    assert second.json()["detail"] == "该thread_id属于其他用户"


def test_research_endpoint_returns_workflow_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, user = register_and_login(client)

    def fake_workflow(
        question: str,
        thread_id: str,
        top_k: int,
        min_score: float,
    ) -> dict:
        assert question == "RT-2如何表示动作？"
        assert thread_id == "research-thread"
        assert top_k == 3
        assert min_score == 0.5
        return {
            "answer": "测试工作流答案。[资料1]",
            "route": "answer",
            "evidence": [{"content": "evidence"}],
            "citations": ["RT-2.pdf，PDF物理页码4"],
            "executed_nodes": [
                "prepare_question",
                "retrieve_evidence",
                "evaluate_evidence",
                "generate_answer",
            ],
        }

    monkeypatch.setattr(
        research_module,
        "run_research_workflow",
        fake_workflow,
    )
    response = client.post(
        "/api/v1/research",
        headers=headers,
        json={
            "question": "RT-2如何表示动作？",
            "thread_id": "research-thread",
            "top_k": 3,
            "min_score": 0.5,
        },
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == user["user_id"]
    assert response.json()["route"] == "answer"
    assert response.json()["evidence_count"] == 1
    assert response.json()["executed_nodes"][-1] == "generate_answer"


def test_research_sse_streams_progress_and_answer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _ = register_and_login(client)

    def fake_stream(**kwargs):
        yield {
            "event": "node",
            "node": "retrieve_evidence",
            "route": None,
            "evidence_count": 2,
        }
        yield {
            "event": "completed",
            "answer": "流式答案",
            "route": "answer",
            "evidence_count": 2,
            "citations": ["RT-2.pdf，PDF物理页码4"],
            "executed_nodes": ["retrieve_evidence", "generate_answer"],
        }

    monkeypatch.setattr(
        research_module,
        "stream_research_workflow",
        fake_stream,
    )
    with client.stream(
        "POST",
        "/api/v1/research/stream",
        headers=headers,
        json={
            "question": "RT-2如何表示动作？",
            "thread_id": "stream-thread",
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )
    assert "event: started" in body
    assert "event: node" in body
    assert "event: completed" in body
    completed_block = next(
        block
        for block in body.replace("\r\n", "\n").split("\n\n")
        if "event: completed" in block
    )
    completed_data = next(
        line.removeprefix("data: ")
        for line in completed_block.splitlines()
        if line.startswith("data: ")
    )
    assert json.loads(completed_data)["answer"] == "流式答案"


def test_chat_request_rejects_empty_question(
    client: TestClient,
) -> None:
    headers, _ = register_and_login(client)
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": ""},
    )
    assert response.status_code == 422


def test_memory_endpoints_are_user_isolated(
    client: TestClient,
    memory_store: InMemoryStore,
) -> None:
    bei_headers, bei = register_and_login(client, "bei-user")
    alice_headers, alice = register_and_login(client, "alice-user")
    memory_store.put(
        build_memory_namespace(bei["user_id"]),
        "memory-1",
        {"category": "preference", "content": "先看结论"},
    )
    memory_store.put(
        build_memory_namespace(alice["user_id"]),
        "memory-2",
        {"category": "preference", "content": "Alice的偏好"},
    )

    bei_response = client.get(
        "/api/v1/users/me/memories",
        headers=bei_headers,
    )
    alice_response = client.get(
        "/api/v1/users/me/memories",
        headers=alice_headers,
    )
    assert bei_response.status_code == 200
    assert [
        item["memory_id"]
        for item in bei_response.json()["memories"]
    ] == ["memory-1"]
    assert [
        item["memory_id"]
        for item in alice_response.json()["memories"]
    ] == ["memory-2"]


def test_memory_update_delete_and_missing(
    client: TestClient,
    memory_store: InMemoryStore,
) -> None:
    headers, user = register_and_login(client)
    namespace = build_memory_namespace(user["user_id"])
    memory_store.put(
        namespace,
        "memory-1",
        {"category": "preference", "content": "旧偏好"},
    )
    update_response = client.put(
        "/api/v1/users/me/memories/memory-1",
        headers=headers,
        json={
            "category": "response_preference",
            "content": "先解释原理",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "先解释原理"

    delete_response = client.delete(
        "/api/v1/users/me/memories/memory-1",
        headers=headers,
    )
    assert delete_response.status_code == 204
    assert memory_store.get(namespace, "memory-1") is None

    missing_response = client.delete(
        "/api/v1/users/me/memories/missing",
        headers=headers,
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "长期记忆不存在"


def test_registration_creates_one_personal_workspace(
    client: TestClient,
) -> None:
    headers, user = register_and_login(
        client,
        username="workspace-user",
    )

    first = client.get("/api/v1/workspaces", headers=headers)
    second = client.get("/api/v1/workspaces", headers=headers)

    assert first.status_code == 200
    assert first.json() == second.json()
    workspaces = first.json()["workspaces"]
    assert len(workspaces) == 1
    assert workspaces[0]["owner_id"] == user["user_id"]
    assert workspaces[0]["role"] == "owner"
    assert workspaces[0]["is_personal"] is True


def test_application_and_agent_version_lifecycle(
    client: TestClient,
) -> None:
    headers, _ = register_and_login(
        client,
        username="application-owner",
    )
    workspace_id = client.get(
        "/api/v1/workspaces",
        headers=headers,
    ).json()["workspaces"][0]["workspace_id"]

    application_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/applications",
        headers=headers,
        json={
            "name": "Research Agent",
            "description": "演示应用",
            "target_type": "internal",
        },
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["application_id"]

    duplicate_application = client.post(
        f"/api/v1/workspaces/{workspace_id}/applications",
        headers=headers,
        json={"name": "Research Agent"},
    )
    assert duplicate_application.status_code == 409

    create_version = client.post(
        f"/api/v1/applications/{application_id}/versions",
        headers=headers,
        json={
            "version": "1.0.0",
            "config_snapshot": {
                "schema_version": "1.0",
                "model": {"provider": "deepseek", "name": "chat"},
                "retrieval": {"top_k": 5},
            },
            "git_commit": "abc1234",
        },
    )
    assert create_version.status_code == 201
    version = create_version.json()
    version_id = version["agent_version_id"]
    assert version["status"] == "draft"

    update_version = client.put(
        f"/api/v1/applications/{application_id}/versions/{version_id}",
        headers=headers,
        json={
            "config_snapshot": {
                "schema_version": "1.0",
                "model": {"provider": "deepseek", "name": "chat"},
                "retrieval": {"top_k": 7},
            },
            "git_commit": "def5678",
        },
    )
    assert update_version.status_code == 200
    assert update_version.json()["config_snapshot"]["retrieval"]["top_k"] == 7

    secret_response = client.put(
        f"/api/v1/applications/{application_id}/versions/{version_id}",
        headers=headers,
        json={
            "config_snapshot": {
                "schema_version": "1.0",
                "provider": {"api_key": "must-not-be-saved"},
            }
        },
    )
    assert secret_response.status_code == 422
    assert "敏感字段" in secret_response.json()["detail"]
    assert "must-not-be-saved" not in secret_response.text

    publish_response = client.post(
        f"/api/v1/applications/{application_id}/versions/{version_id}/publish",
        headers=headers,
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "published"
    assert publish_response.json()["published_at"] is not None

    immutable_response = client.put(
        f"/api/v1/applications/{application_id}/versions/{version_id}",
        headers=headers,
        json={
            "config_snapshot": {
                "schema_version": "1.0",
                "retrieval": {"top_k": 10},
            }
        },
    )
    assert immutable_response.status_code == 409
    assert "不可修改" in immutable_response.json()["detail"]

    duplicate_version = client.post(
        f"/api/v1/applications/{application_id}/versions",
        headers=headers,
        json={
            "version": "1.0.0",
            "config_snapshot": {"schema_version": "1.0"},
        },
    )
    assert duplicate_version.status_code == 409

    versions_response = client.get(
        f"/api/v1/applications/{application_id}/versions",
        headers=headers,
    )
    assert versions_response.status_code == 200
    assert len(versions_response.json()["versions"]) == 1

    audit_response = client.get(
        "/api/v1/users/me/audit-events?limit=50",
        headers=headers,
    )
    event_types = {
        item["event_type"] for item in audit_response.json()["events"]
    }
    assert {
        "application.created",
        "agent_version.created",
        "agent_version.updated",
        "agent_version.published",
    } <= event_types


def test_workspace_and_application_are_isolated_between_users(
    client: TestClient,
) -> None:
    owner_headers, _ = register_and_login(
        client,
        username="workspace-owner",
    )
    owner_workspace = client.get(
        "/api/v1/workspaces",
        headers=owner_headers,
    ).json()["workspaces"][0]
    application = client.post(
        f"/api/v1/workspaces/{owner_workspace['workspace_id']}/applications",
        headers=owner_headers,
        json={"name": "Private Agent", "target_type": "mcp"},
    ).json()
    version = client.post(
        f"/api/v1/applications/{application['application_id']}/versions",
        headers=owner_headers,
        json={
            "version": "1.0.0",
            "config_snapshot": {"schema_version": "1.0"},
        },
    ).json()

    other_headers, _ = register_and_login(
        client,
        username="other-workspace-user",
    )
    other_workspaces = client.get(
        "/api/v1/workspaces",
        headers=other_headers,
    ).json()["workspaces"]
    assert len(other_workspaces) == 1
    assert other_workspaces[0]["workspace_id"] != owner_workspace["workspace_id"]

    list_foreign = client.get(
        f"/api/v1/workspaces/{owner_workspace['workspace_id']}/applications",
        headers=other_headers,
    )
    create_foreign = client.post(
        f"/api/v1/workspaces/{owner_workspace['workspace_id']}/applications",
        headers=other_headers,
        json={"name": "Intruder Agent"},
    )
    list_foreign_versions = client.get(
        f"/api/v1/applications/{application['application_id']}/versions",
        headers=other_headers,
    )
    update_foreign_version = client.put(
        f"/api/v1/applications/{application['application_id']}/versions/"
        f"{version['agent_version_id']}",
        headers=other_headers,
        json={"config_snapshot": {"schema_version": "2.0"}},
    )
    publish_foreign_version = client.post(
        f"/api/v1/applications/{application['application_id']}/versions/"
        f"{version['agent_version_id']}/publish",
        headers=other_headers,
    )

    assert list_foreign.status_code == 404
    assert create_foreign.status_code == 404
    assert list_foreign_versions.status_code == 404
    assert update_foreign_version.status_code == 404
    assert publish_foreign_version.status_code == 404


def test_openapi_contains_workspace_and_agent_version_routes(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/workspaces" in paths
    assert "/api/v1/workspaces/{workspace_id}/applications" in paths
    assert "/api/v1/applications/{application_id}/versions" in paths
    assert (
        "/api/v1/applications/{application_id}/versions/"
        "{agent_version_id}/publish"
    ) in paths


def test_evaluation_dataset_and_rubric_lifecycle(client: TestClient) -> None:
    headers, _ = register_and_login(client, username="catalog-owner")
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()["workspaces"][0]["workspace_id"]
    dataset = client.post(f"/api/v1/workspaces/{workspace_id}/evaluation-datasets", headers=headers, json={"name": "qa-demo", "description": "QA cases"})
    assert dataset.status_code == 201
    dataset_id = dataset.json()["dataset_id"]
    version = client.post(f"/api/v1/evaluation-datasets/{dataset_id}/versions", headers=headers, json={"version": "1.0.0", "environment": "demo"})
    assert version.status_code == 201
    version_id = version.json()["dataset_version_id"]
    assert client.post(f"/api/v1/evaluation-datasets/{dataset_id}/versions/{version_id}/publish", headers=headers).status_code == 422
    case = client.post(f"/api/v1/evaluation-datasets/{dataset_id}/versions/{version_id}/cases", headers=headers, json={"external_id": "case-1", "input": {"question": "什么是不可变版本？"}, "expected": {"keywords": ["发布", "不可修改"]}, "metadata": {"language": "zh"}})
    assert case.status_code == 201
    case_id = case.json()["case_id"]
    updated = client.put(f"/api/v1/evaluation-datasets/{dataset_id}/versions/{version_id}/cases/{case_id}", headers=headers, json={"external_id": "case-1", "input": {"question": "发布版本可以原地修改吗？"}, "expected": {"answer": "不可以"}})
    assert updated.status_code == 200
    published = client.post(f"/api/v1/evaluation-datasets/{dataset_id}/versions/{version_id}/publish", headers=headers)
    assert published.status_code == 200
    assert len(published.json()["content_hash"]) == 64
    immutable = client.put(f"/api/v1/evaluation-datasets/{dataset_id}/versions/{version_id}/cases/{case_id}", headers=headers, json={"external_id": "case-1", "input": {"question": "changed"}, "expected": {"answer": "changed"}})
    assert immutable.status_code == 409

    rubric = client.post(f"/api/v1/workspaces/{workspace_id}/rubrics", headers=headers, json={"name": "answer-quality"})
    assert rubric.status_code == 201
    rubric_id = rubric.json()["rubric_id"]
    rubric_version = client.post(f"/api/v1/rubrics/{rubric_id}/versions", headers=headers, json={"version": "1.0.0", "environment": "demo", "instructions": "依据证据评分。"})
    assert rubric_version.status_code == 201
    rubric_version_id = rubric_version.json()["rubric_version_id"]
    criterion = client.post(f"/api/v1/rubrics/{rubric_id}/versions/{rubric_version_id}/criteria", headers=headers, json={"key": "faithfulness", "title": "忠实度", "min_score": 1, "max_score": 5, "weight": 1, "required": True})
    assert criterion.status_code == 201
    rubric_published = client.post(f"/api/v1/rubrics/{rubric_id}/versions/{rubric_version_id}/publish", headers=headers)
    assert rubric_published.status_code == 200
    assert len(rubric_published.json()["content_hash"]) == 64
    immutable_criterion = client.delete(f"/api/v1/rubrics/{rubric_id}/versions/{rubric_version_id}/criteria/{criterion.json()['criterion_id']}", headers=headers)
    assert immutable_criterion.status_code == 409

    audit_types = {row["event_type"] for row in client.get("/api/v1/users/me/audit-events?limit=50", headers=headers).json()["events"]}
    assert {"evaluation_dataset.created", "evaluation_dataset_version.created", "evaluation_dataset_version.published", "rubric.created", "rubric_version.created", "rubric_version.published"} <= audit_types


def test_evaluation_catalog_isolated_between_users(client: TestClient) -> None:
    owner_headers, _ = register_and_login(client, username="catalog-private-owner")
    workspace_id = client.get("/api/v1/workspaces", headers=owner_headers).json()["workspaces"][0]["workspace_id"]
    dataset = client.post(f"/api/v1/workspaces/{workspace_id}/evaluation-datasets", headers=owner_headers, json={"name": "private-cases"}).json()
    version = client.post(
        f"/api/v1/evaluation-datasets/{dataset['dataset_id']}/versions",
        headers=owner_headers,
        json={"version": "1.0.0", "environment": "test"},
    ).json()
    rubric = client.post(f"/api/v1/workspaces/{workspace_id}/rubrics", headers=owner_headers, json={"name": "private-rubric"}).json()
    other_headers, _ = register_and_login(client, username="catalog-intruder")
    assert client.get(f"/api/v1/workspaces/{workspace_id}/evaluation-datasets", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/evaluation-datasets/{dataset['dataset_id']}/versions", headers=other_headers).status_code == 404
    assert client.post(
        f"/api/v1/evaluation-datasets/{dataset['dataset_id']}/versions/"
        f"{version['dataset_version_id']}/cases",
        headers=other_headers,
        json={
            "external_id": "injected",
            "input": {"question": "foreign"},
            "expected": {"answer": "foreign"},
        },
    ).status_code == 404
    owner_cases = client.get(
        f"/api/v1/evaluation-datasets/{dataset['dataset_id']}/versions/"
        f"{version['dataset_version_id']}/cases",
        headers=owner_headers,
    )
    assert owner_cases.json()["cases"] == []
    assert client.get(f"/api/v1/rubrics/{rubric['rubric_id']}/versions", headers=other_headers).status_code == 404


def test_openapi_contains_evaluation_catalog_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/workspaces/{workspace_id}/evaluation-datasets" in paths
    assert "/api/v1/evaluation-datasets/{dataset_id}/versions/{version_id}/cases" in paths
    assert "/api/v1/workspaces/{workspace_id}/rubrics" in paths
    assert "/api/v1/rubrics/{rubric_id}/versions/{version_id}/criteria" in paths


def test_evaluation_run_create_list_detail_and_isolation(client: TestClient) -> None:
    headers, _ = register_and_login(client, username="run-owner")
    workspace_id = client.get(
        "/api/v1/workspaces", headers=headers
    ).json()["workspaces"][0]["workspace_id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/evaluation-runs",
        headers=headers,
        json={
            "agent_version_id": "published-agent",
            "dataset_version_id": "published-dataset",
            "trigger_type": "api",
            "config_snapshot": {
                "schema_version": "1.0",
                "evaluators": ["answer_quality"],
            },
            "git_commit": "abc123",
        },
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    assert created.json()["status"] == "created"
    runs = client.get(
        f"/api/v1/workspaces/{workspace_id}/evaluation-runs",
        headers=headers,
    ).json()["runs"]
    assert len(runs) == 1
    detail = client.get(f"/api/v1/evaluation-runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["results"] == []
    assert detail.json()["metrics"] == []
    secret = client.post(
        f"/api/v1/workspaces/{workspace_id}/evaluation-runs",
        headers=headers,
        json={
            "agent_version_id": "a",
            "dataset_version_id": "d",
            "config_snapshot": {"api_key": "do-not-store"},
        },
    )
    assert secret.status_code == 422
    assert "do-not-store" not in secret.text
    other_headers, _ = register_and_login(client, username="run-other")
    assert client.get(
        f"/api/v1/evaluation-runs/{run_id}", headers=other_headers
    ).status_code == 404


def test_openapi_contains_evaluation_run_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/workspaces/{workspace_id}/evaluation-runs" in paths
    assert "/api/v1/evaluation-runs/{run_id}" in paths


def test_owner_can_add_workspace_reviewer(client: TestClient) -> None:
    owner_headers, _ = register_and_login(client, username="review-owner")
    reviewer_headers, reviewer = register_and_login(
        client, username="review-member"
    )
    workspace_id = client.get(
        "/api/v1/workspaces", headers=owner_headers
    ).json()["workspaces"][0]["workspace_id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/reviewers",
        headers=owner_headers,
        json={"username": "review-member"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "reviewer"
    assert response.json()["owner_id"] != reviewer["user_id"]
    reviewer_workspaces = client.get(
        "/api/v1/workspaces", headers=reviewer_headers
    ).json()["workspaces"]
    assert any(
        item["workspace_id"] == workspace_id and item["role"] == "reviewer"
        for item in reviewer_workspaces
    )


def test_complete_human_review_revision_workflow(
    client: TestClient,
    review_repository: InMemoryReviewRepository,
) -> None:
    headers, _ = register_and_login(client, username="human-reviewer")
    now = datetime.now(timezone.utc)
    review_repository.seed_context(
        run_id="ready-run",
        rubric_version_id="published-rubric",
        case_results=[
            ReviewCaseRecord(
                review_id="review-1",
                case_result_id="case-result-1",
                external_id="demo-1",
                input_json={"question": "是否有依据？"},
                expected_json={"expected_route": "answer"},
                output_json={"answer": "有依据 [资料1]"},
                evidence_json=[{"source": "doc.md"}],
                review_status="pending",
                latest_revision=0,
            )
        ],
        criteria=[
            ReviewCriterionRecord(
                "criterion-faithfulness",
                "faithfulness",
                "忠实度",
                "是否忠实于证据",
                1,
                5,
                0.6,
                True,
            ),
            ReviewCriterionRecord(
                "criterion-completeness",
                "completeness",
                "完整度",
                "是否覆盖关键点",
                1,
                5,
                0.4,
                True,
            ),
        ],
    )
    task = client.post(
        "/api/v1/evaluation-runs/ready-run/review-tasks",
        headers=headers,
        json={
            "rubric_version_id": "published-rubric",
            "name": "Demo人工评审",
        },
    )
    assert task.status_code == 201
    task_id = task.json()["task_id"]
    assert task.json()["pending_count"] == 1
    assert len(
        client.get("/api/v1/review-tasks/mine", headers=headers).json()[
            "tasks"
        ]
    ) == 1

    draft_payload = {
        "expected_revision": 0,
        "overall_comment": "先保存部分结果",
        "scores": [
            {
                "criterion_id": "criterion-faithfulness",
                "score": 4,
                "comment": "证据基本支持",
            }
        ],
    }
    draft = client.put(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/draft",
        headers={**headers, "Idempotency-Key": "draft-save-1"},
        json=draft_payload,
    )
    assert draft.status_code == 200
    assert draft.json()["revision"] == 1
    retry = client.put(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/draft",
        headers={**headers, "Idempotency-Key": "draft-save-1"},
        json=draft_payload,
    )
    assert retry.status_code == 200
    assert retry.json()["revision_id"] == draft.json()["revision_id"]
    stale = client.put(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/draft",
        headers={**headers, "Idempotency-Key": "draft-stale"},
        json=draft_payload,
    )
    assert stale.status_code == 409
    reopened = client.get(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1",
        headers=headers,
    )
    assert reopened.json()["case"]["review_status"] == "draft"
    assert reopened.json()["revisions"][-1]["scores"][0]["score"] == 4

    incomplete = client.post(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/submit",
        headers={**headers, "Idempotency-Key": "submit-incomplete"},
        json={**draft_payload, "expected_revision": 1},
    )
    assert incomplete.status_code == 422
    complete_scores = [
        draft_payload["scores"][0],
        {
            "criterion_id": "criterion-completeness",
            "score": 5,
            "comment": "覆盖完整",
        },
    ]
    submitted = client.post(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/submit",
        headers={**headers, "Idempotency-Key": "submit-1"},
        json={
            "expected_revision": 1,
            "overall_comment": "可以提交",
            "scores": complete_scores,
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["revision"] == 2
    assert submitted.json()["status"] == "submitted"
    assert client.get(
        f"/api/v1/review-tasks/{task_id}", headers=headers
    ).json()["task"]["status"] == "completed"
    assert client.put(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/draft",
        headers=headers,
        json={"expected_revision": 2, "scores": complete_scores},
    ).status_code == 409

    correction = client.post(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/revisions",
        headers={**headers, "Idempotency-Key": "correction-1"},
        json={"expected_revision": 2, "reason": "修正完整度评分"},
    )
    assert correction.status_code == 201
    assert correction.json()["revision"] == 3
    assert correction.json()["status"] == "draft"
    assert len(correction.json()["scores"]) == 2
    corrected_scores = [complete_scores[0], {**complete_scores[1], "score": 4}]
    corrected = client.post(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/submit",
        headers={**headers, "Idempotency-Key": "submit-correction"},
        json={
            "expected_revision": 3,
            "overall_comment": "修正后提交",
            "reason": "评分调整",
            "scores": corrected_scores,
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["revision"] == 4
    detail = client.get(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1",
        headers=headers,
    ).json()
    statuses = [item["status"] for item in detail["revisions"]]
    assert statuses == ["superseded", "superseded", "superseded", "submitted"]

    other_headers, _ = register_and_login(client, username="review-intruder")
    assert client.get(
        f"/api/v1/review-tasks/{task_id}", headers=other_headers
    ).status_code == 404
    assert client.put(
        f"/api/v1/review-tasks/{task_id}/cases/case-result-1/draft",
        headers=other_headers,
        json={"expected_revision": 4, "scores": []},
    ).status_code == 404


def test_review_ui_and_openapi_routes(client: TestClient) -> None:
    page = client.get("/review")
    assert page.status_code == 200
    assert "ResearchFlow 人工评审" in page.text
    assert "textContent" in page.text
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/review-tasks/mine" in paths
    assert "/api/v1/review-tasks/{task_id}/cases/{case_result_id}/draft" in paths
    assert "/api/v1/review-tasks/{task_id}/cases/{case_result_id}/submit" in paths


def test_statistics_report_generation_and_isolation(
    client: TestClient,
    reporting_repository: InMemoryReportingRepository,
) -> None:
    headers, user = register_and_login(client, username="report-owner")
    reporting_repository.seed_snapshot("report-run", user["user_id"], reporting_snapshot())
    reporting_repository.snapshots["report-run"][1]["run"]["run_id"] = "report-run"
    summary = client.get("/api/v1/evaluation-runs/report-run/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["program_metrics"][0]["source"] == "program"
    assert summary.json()["human_metrics"][0]["source"] == "human"
    generated = client.post("/api/v1/evaluation-runs/report-run/reports", headers=headers)
    assert generated.status_code == 201
    reports = generated.json()["reports"]
    assert {x["format"] for x in reports} == {"json", "html"}
    assert all(x["status"] == "completed" and x["content_url"] for x in reports)
    content = client.get(reports[0]["content_url"], headers=headers)
    assert content.status_code == 200
    listed = client.get("/api/v1/evaluation-runs/report-run/reports", headers=headers)
    assert len(listed.json()["reports"]) == 2
    other_headers, _ = register_and_login(client, username="report-intruder")
    assert client.get("/api/v1/evaluation-runs/report-run/summary", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/reports/{reports[0]['report_id']}", headers=other_headers).status_code == 404


def test_openapi_contains_statistics_and_report_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/evaluation-runs/{run_id}/summary" in paths
    assert "/api/v1/evaluation-runs/{run_id}/reports" in paths
    assert "/api/v1/reports/{report_id}/content" in paths


def test_baseline_gate_policy_evaluation_and_report(
    client: TestClient,
    gate_repository: InMemoryGateRepository,
    reporting_repository: InMemoryReportingRepository,
) -> None:
    headers,user=register_and_login(client,username="gate-owner")
    owner=user["user_id"];workspace_id=client.get("/api/v1/workspaces",headers=headers).json()["workspaces"][0]["workspace_id"]
    from tests.unit.test_quality_gates import complete_snapshot
    for run_id in ("baseline-run","candidate-run"):
        gate_repository.seed_run(run_id,"app-1",workspace_id,owner)
        reporting_repository.seed_snapshot(run_id,owner,complete_snapshot(run_id))
    baseline=client.put("/api/v1/applications/app-1/baseline",headers=headers,json={"run_id":"baseline-run"})
    assert baseline.status_code==200 and baseline.json()["active"] is True
    policy=client.post(f"/api/v1/workspaces/{workspace_id}/gate-policies",headers=headers,json={
        "name":"release","version":"1.0","rules":[
            {"rule_id":"min","source":"program","namespace_key":"quality@1.0","metric_key":"correct","kind":"absolute_min","min_value":0.4},
            {"rule_id":"drop","source":"program","namespace_key":"quality@1.0","metric_key":"correct","kind":"max_regression","max_drop":0.1}
        ]})
    assert policy.status_code==201
    policy_id=policy.json()["policy_id"]
    assert client.post(f"/api/v1/gate-policies/{policy_id}/publish",headers=headers).status_code==200
    evaluated=client.post("/api/v1/evaluation-runs/candidate-run/gate-evaluations",headers=headers,json={"policy_id":policy_id})
    assert evaluated.status_code==201 and evaluated.json()["status"]=="passed"
    again=client.post("/api/v1/evaluation-runs/candidate-run/gate-evaluations",headers=headers,json={"policy_id":policy_id})
    assert again.json()["results"]==evaluated.json()["results"]
    reports=client.post("/api/v1/evaluation-runs/candidate-run/reports",headers=headers).json()["reports"]
    json_report=next(x for x in reports if x["format"]=="json")
    content=client.get(json_report["content_url"],headers=headers).json()
    assert content["gate"]["status"]=="passed"
    html_report=next(x for x in reports if x["format"]=="html")
    html=client.get(html_report["content_url"],headers=headers)
    assert "结论：passed" in html.text and "baseline-run" in html.text
    other_headers,_=register_and_login(client,username="gate-other")
    assert client.post("/api/v1/evaluation-runs/candidate-run/gate-evaluations",headers=other_headers,json={"policy_id":policy_id}).status_code==404


def test_gate_without_baseline_is_incomplete(
    client: TestClient,gate_repository:InMemoryGateRepository,
    reporting_repository:InMemoryReportingRepository,
) -> None:
    headers,user=register_and_login(client,username="gate-incomplete")
    owner=user["user_id"];workspace_id=client.get("/api/v1/workspaces",headers=headers).json()["workspaces"][0]["workspace_id"]
    from tests.unit.test_quality_gates import complete_snapshot
    gate_repository.seed_run("no-baseline","app-none",workspace_id,owner)
    reporting_repository.seed_snapshot("no-baseline",owner,complete_snapshot("no-baseline"))
    policy=client.post(f"/api/v1/workspaces/{workspace_id}/gate-policies",headers=headers,json={"name":"release","version":"1","rules":[{"rule_id":"min","source":"program","namespace_key":"quality@1.0","metric_key":"correct","kind":"absolute_min","min_value":0.4}]}).json()
    client.post(f"/api/v1/gate-policies/{policy['policy_id']}/publish",headers=headers)
    result=client.post("/api/v1/evaluation-runs/no-baseline/gate-evaluations",headers=headers,json={"policy_id":policy["policy_id"]})
    assert result.status_code==201 and result.json()["status"]=="incomplete"


def test_openapi_contains_quality_gate_routes(client: TestClient) -> None:
    paths=client.get("/openapi.json").json()["paths"]
    assert "/api/v1/applications/{application_id}/baseline" in paths
    assert "/api/v1/workspaces/{workspace_id}/gate-policies" in paths
    assert "/api/v1/evaluation-runs/{run_id}/gate-evaluations" in paths
