from app.api.routers.audit import router as audit_router
from app.api.routers.auth import router as auth_router
from app.api.routers.chat import router as chat_router
from app.api.routers.health import router as health_router
from app.api.routers.memories import router as memories_router
from app.api.routers.research import router as research_router
from app.api.routers.workspaces import router as workspaces_router
from app.api.routers.evaluation_catalog import router as evaluation_catalog_router
from app.api.routers.evaluation_runs import router as evaluation_runs_router
from app.api.routers.reviews import router as reviews_router
from app.api.routers.review_ui import router as review_ui_router
from app.api.routers.reports import router as reports_router
from app.api.routers.gates import router as gates_router


__all__ = [
    "audit_router",
    "auth_router",
    "chat_router",
    "health_router",
    "memories_router",
    "research_router",
    "workspaces_router",
    "evaluation_catalog_router",
    "evaluation_runs_router",
    "reviews_router",
    "review_ui_router",
    "reports_router",
    "gates_router",
]
