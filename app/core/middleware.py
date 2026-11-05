"""请求 ID、审计日志与简单令牌桶限流。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import Settings, get_settings
from app.core.request_context import request_id_var, route_var, tenant_id_var

logger = logging.getLogger("matpilot.audit")

# Paid / heavy routes — tighter bucket when RATE_LIMIT is enabled.
COSTLY_PREFIXES = (
    "/api/v1/agent",
    "/api/v1/jobs",
    "/api/v1/knowledge",
    "/api/v1/documents",
    "/api/v1/materials",
    "/api/v1/literature",
)


class _TokenBucket:
    def __init__(self, rate_per_minute: int) -> None:
        self.capacity = max(1, rate_per_minute)
        self.tokens = float(self.capacity)
        self.rate = self.capacity / 60.0
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(request_id)
        route_var.set(f"{request.method} {request.url.path}")
        tenant_id_var.set("-")
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            status = response.status_code if response is not None else 500
            if response is not None:
                response.headers["X-Request-ID"] = request_id
            logger.info(
                "audit method=%s path=%s status=%s elapsed_ms=%s",
                request.method,
                request.url.path,
                status,
                elapsed_ms,
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings
        configured = settings or get_settings()
        self.enabled = configured.rate_limit_per_minute > 0
        self.global_bucket = _TokenBucket(configured.rate_limit_per_minute or 60)
        self.costly_bucket = _TokenBucket(max(1, configured.rate_limit_costly_per_minute))

    def _rate_limited(self, code: str, message: str) -> JSONResponse:
        request_id = request_id_var.get() or "-"
        return JSONResponse(
            status_code=429,
            content={"error": {"code": code, "message": message, "request_id": request_id}},
            headers={"X-Request-ID": request_id},
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled or request.url.path.startswith("/health"):
            return await call_next(request)
        if not self.global_bucket.allow():
            return self._rate_limited("rate_limited", "请求过于频繁，请稍后再试。")
        if request.url.path.startswith(COSTLY_PREFIXES) and request.method in {
            "POST",
            "PUT",
            "PATCH",
        }:
            if not self.costly_bucket.allow():
                return self._rate_limited(
                    "rate_limited_costly",
                    "付费或长任务接口请求过于频繁，请稍后再试。",
                )
        return await call_next(request)
