import json
from pathlib import Path

from app.evaluation import InMemoryEvaluationCatalogRepository
from app.evaluation.catalog_importer import import_dataset_payload, import_rubric_payload
from app.workspaces import InMemoryWorkspaceRepository


ROOT = Path(__file__).resolve().parents[2]


def _repository():
    workspaces = InMemoryWorkspaceRepository()
    workspace = workspaces.ensure_personal_workspace("user-1", "owner")
    return InMemoryEvaluationCatalogRepository(workspaces), workspace


def test_demo_dataset_import_is_idempotent() -> None:
    repository, workspace = _repository()
    payload = json.loads((ROOT / "evaluations/demo/evaluation_dataset.json").read_text(encoding="utf-8"))
    first = import_dataset_payload(repository, workspace_id=workspace.workspace_id, user_id="user-1", payload=payload)
    second = import_dataset_payload(repository, workspace_id=workspace.workspace_id, user_id="user-1", payload=payload)
    assert first.dataset_version_id == second.dataset_version_id
    assert first.content_hash == second.content_hash
    assert len(repository.list_dataset_versions(first.dataset_id, "user-1")) == 1
    assert len(repository.list_cases(first.dataset_id, first.dataset_version_id, "user-1")) == 4


def test_demo_rubric_import_is_idempotent() -> None:
    repository, workspace = _repository()
    payload = json.loads((ROOT / "evaluations/demo/rubric.json").read_text(encoding="utf-8"))
    first = import_rubric_payload(repository, workspace_id=workspace.workspace_id, user_id="user-1", payload=payload)
    second = import_rubric_payload(repository, workspace_id=workspace.workspace_id, user_id="user-1", payload=payload)
    assert first.rubric_version_id == second.rubric_version_id
    assert first.content_hash == second.content_hash
    assert len(repository.list_rubric_versions(first.rubric_id, "user-1")) == 1
    assert len(repository.list_criteria(first.rubric_id, first.rubric_version_id, "user-1")) == 3
