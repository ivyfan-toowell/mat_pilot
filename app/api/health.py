"""进程存活与就绪检查。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.services.vector_store import VectorStore

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness only: does not claim that external APIs or PostgreSQL are ready."""
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
def ready(settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    checks = {
        "llm_configured": bool(settings.dashscope_api_key),
        "materials_configured": bool(settings.mp_api_key),
        "openalex_configured": bool(settings.openalex_api_key),
    }
    try:
        with VectorStore(settings).connect() as connection:
            connection.execute("SELECT 1")
        checks["database"] = "ready"
    except ServiceError as exc:
        checks["database"] = exc.code
    healthy = all(
        (checks["llm_configured"], checks["materials_configured"], checks["database"] == "ready")
    )
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
