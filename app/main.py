"""创建 FastAPI 应用，注册业务路由、日志及统一异常处理。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.agent import router as agent_router
from app.api.documents import router as documents_router
from app.api.experimental_knowledge import router as experimental_knowledge_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.knowledge import router as knowledge_router
from app.api.literature import router as literature_router
from app.api.materials import router as materials_router
from app.core.config import get_settings
from app.core.errors import ServiceError
from app.core.logging import configure_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.core.request_context import request_id_var
from app.services.job_service import get_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.log_json)
    if settings.schema_auto_apply and settings.database_url:
        from app.services.schema import apply_schema

        try:
            apply_schema(settings)
        except ServiceError as exc:
            logger.warning("schema auto-apply skipped: %s", exc.code)
    worker = get_worker()
    worker.start(settings.job_workers)
    logger.info("MatPilot starting version=%s job_workers=%s", __version__, settings.job_workers)
    yield
    worker.stop()
    logger.info("MatPilot shutdown")


app = FastAPI(title="MatPilot", version=__version__, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware, settings=get_settings())
app.add_middleware(RequestContextMiddleware)

for router in (
    materials_router,
    documents_router,
    experimental_knowledge_router,
    knowledge_router,
    literature_router,
    agent_router,
    jobs_router,
):
    app.include_router(router)
app.include_router(health_router)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id_var.get(),
            }
        },
        headers={"X-Request-ID": request_id_var.get()},
    )
