"""创建 FastAPI 应用，注册业务路由、日志及统一异常处理。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.agent import router as agent_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.literature import router as literature_router
from app.api.materials import router as materials_router
from app.core.config import get_settings
from app.core.errors import ServiceError
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("MatPilot starting version=%s", __version__)
    yield
    logger.info("MatPilot shutdown")


app = FastAPI(title="MatPilot", version=__version__, lifespan=lifespan)
app.include_router(materials_router)
app.include_router(documents_router)
app.include_router(knowledge_router)
app.include_router(literature_router)
app.include_router(agent_router)
app.include_router(health_router)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness only: does not claim that external APIs or PostgreSQL are ready."""
    return {"status": "ok", "version": __version__}
