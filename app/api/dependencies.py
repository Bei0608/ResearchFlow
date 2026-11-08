from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from langgraph.store.base import BaseStore

from app.memory import get_postgres_store
from app.evaluation import (
    EvaluationCatalogRepository,
    get_evaluation_catalog_repository,
    get_evaluation_run_repository,
)
from app.evaluation.runs import EvaluationRunRepository
from app.evaluation.reviews import ReviewRepository, get_review_repository
from app.evaluation.reporting import ReportingRepository, get_reporting_repository
from app.evaluation.gates import GateRepository, get_gate_repository
from app.applications import (
    ApplicationRepository,
    get_application_repository,
)
from app.security import (
    IdentityRepository,
    JWTSettings,
    UserRecord,
    decode_access_token,
    get_identity_repository,
    get_jwt_settings,
)
from app.workspaces import (
    WorkspaceRepository,
    get_workspace_repository,
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token"
)


def provide_memory_store() -> BaseStore:
    """向API路由提供长期记忆Store，测试时可覆盖。"""
    return get_postgres_store()


def provide_identity_repository() -> IdentityRepository:
    """提供用户身份与thread归属仓库。"""
    return get_identity_repository()


def provide_workspace_repository() -> WorkspaceRepository:
    """提供Workspace成员作用域仓库。"""
    return get_workspace_repository()


def provide_application_repository() -> ApplicationRepository:
    """提供Agent应用和版本仓库。"""
    return get_application_repository()


def provide_evaluation_catalog_repository() -> EvaluationCatalogRepository:
    """提供评测集、案例、量表和准则仓库。"""
    return get_evaluation_catalog_repository()


def provide_evaluation_run_repository() -> EvaluationRunRepository:
    """提供程序评测运行与指标仓库。"""
    return get_evaluation_run_repository()


def provide_review_repository() -> ReviewRepository:
    """提供人工评审任务、修订和评分仓库。"""
    return get_review_repository()


def provide_reporting_repository() -> ReportingRepository:
    """提供统计投影和报告仓库。"""
    return get_reporting_repository()


def provide_gate_repository() -> GateRepository:
    """提供Baseline、Gate Policy和Gate Evaluation仓库。"""
    return get_gate_repository()


def provide_jwt_settings() -> JWTSettings:
    """提供JWT配置，测试时可覆盖。"""
    return get_jwt_settings()


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    settings: Annotated[
        JWTSettings,
        Depends(provide_jwt_settings),
    ],
) -> UserRecord:
    """验证Bearer Token并加载当前用户。"""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token, settings)
        user_id = str(payload["sub"])
    except (KeyError, ValueError):
        raise credentials_error from None

    user = repository.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_thread_owner(
    thread_id: str,
    user: UserRecord,
    repository: IdentityRepository,
) -> None:
    """占有新thread或验证现有thread属于当前用户。"""
    if not repository.claim_thread(thread_id, user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该thread_id属于其他用户",
        )
