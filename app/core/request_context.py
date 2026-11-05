"""请求级上下文：request_id 与租户，供日志和审计读取。"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="-")
route_var: ContextVar[str] = ContextVar("route", default="-")
