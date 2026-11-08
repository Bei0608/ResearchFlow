import logging
from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.routers import (
    audit_router,
    auth_router,
    chat_router,
    health_router,
    memories_router,
    research_router,
    workspaces_router,
    evaluation_catalog_router,
    evaluation_runs_router,
    reviews_router,
    review_ui_router,
    reports_router,
    gates_router,
)
from app.api.rate_limit import (
    RateLimiter,
    RateLimitSettings,
    build_rate_limiter,
    get_rate_limit_settings,
)
from app.observability import configure_logging
from app.observability.metrics import (
    HTTP_DURATION,
    HTTP_IN_PROGRESS,
    HTTP_REQUESTS,
    RATE_LIMIT_REJECTIONS,
)


logger = logging.getLogger("researchflow.api")


def create_app(
    rate_limit_settings: RateLimitSettings | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """创建ResearchFlow HTTP应用。"""
    configure_logging()
    application = FastAPI(
        title="ResearchFlow API",
        description=(
            "具身智能论文RAG、Agent、LangGraph工作流"
            "、持久化记忆与Agent评测平台服务"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
        ],
    )
    application.mount("/metrics", make_asgi_app())
    limiter = rate_limiter or build_rate_limiter(
        rate_limit_settings or get_rate_limit_settings()
    )

    @application.middleware("http")
    async def rate_limit_requests(
        request: Request,
        call_next: Callable,
    ):
        excluded_prefixes = (
            "/api/v1/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        )
        if request.url.path.startswith(excluded_prefixes):
            return await call_next(request)

        client_host = (
            request.client.host
            if request.client is not None
            else "unknown"
        )
        allowed, remaining, retry_after = limiter.check(
            client_host
        )
        if not allowed:
            RATE_LIMIT_REJECTIONS.inc()
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试"},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Remaining": "0",
                },
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(
            remaining
        )
        return response

    @application.middleware("http")
    async def request_observability(
        request: Request,
        call_next,
    ):
        request_id = (
            request.headers.get("X-Request-ID")
            or uuid4().hex
        )
        request.state.request_id = request_id
        started_at = perf_counter()
        HTTP_IN_PROGRESS.inc()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = perf_counter() - started_at
            route = request.scope.get("route")
            route_path = getattr(
                route,
                "path",
                request.url.path,
            )
            HTTP_REQUESTS.labels(
                method=request.method,
                route=route_path,
                status=str(status_code),
            ).inc()
            HTTP_DURATION.labels(
                method=request.method,
                route=route_path,
            ).observe(duration)
            HTTP_IN_PROGRESS.dec()

            logger.info(
                "HTTP请求 method=%s path=%s status=%s "
                "duration=%.3fs request_id=%s",
                request.method,
                request.url.path,
                status_code,
                duration,
                request_id,
            )

    application.include_router(
        health_router,
        prefix="/api/v1",
    )
    application.include_router(
        auth_router,
        prefix="/api/v1",
    )
    application.include_router(
        chat_router,
        prefix="/api/v1",
    )
    application.include_router(
        research_router,
        prefix="/api/v1",
    )
    application.include_router(
        memories_router,
        prefix="/api/v1",
    )
    application.include_router(
        audit_router,
        prefix="/api/v1",
    )
    application.include_router(
        workspaces_router,
        prefix="/api/v1",
    )
    application.include_router(
        evaluation_catalog_router,
        prefix="/api/v1",
    )
    application.include_router(
        evaluation_runs_router,
        prefix="/api/v1",
    )
    application.include_router(
        reviews_router,
        prefix="/api/v1",
    )
    application.include_router(review_ui_router)
    application.include_router(reports_router, prefix="/api/v1")
    application.include_router(gates_router, prefix="/api/v1")

    return application


app = create_app()
