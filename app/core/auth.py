"""API Key 认证与当前请求主体（租户）解析。"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import LOCAL_TENANT_ID, TENANT_ID_PATTERN, Settings, get_settings
from app.core.errors import ServiceError
from app.core.request_context import tenant_id_var


@dataclass(frozen=True, slots=True)
class Principal:
    tenant_id: str
    subject: str


def parse_api_keys(raw: str) -> dict[str, str]:
    """Parse AUTH_API_KEYS as tenant_id:key pairs. Returns key -> tenant_id."""
    mapping: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        tenant_id, separator, key = item.partition(":")
        if not separator or not tenant_id or not key:
            raise ValueError("AUTH_API_KEYS entries must be tenant_id:key")
        if not TENANT_ID_PATTERN.fullmatch(tenant_id):
            raise ValueError(f"invalid tenant_id in AUTH_API_KEYS: {tenant_id}")
        if key in mapping:
            raise ValueError("duplicate API key in AUTH_API_KEYS")
        mapping[key] = tenant_id
    return mapping


def require_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if settings.auth_mode == "off":
        principal = Principal(tenant_id=LOCAL_TENANT_ID, subject="local")
        tenant_id_var.set(principal.tenant_id)
        return principal
    try:
        keys = parse_api_keys(settings.auth_api_keys)
    except ValueError as exc:
        raise ServiceError("auth_misconfigured", str(exc), 503) from exc
    if not keys:
        raise ServiceError(
            "auth_misconfigured", "AUTH_MODE=api_key 时必须配置 AUTH_API_KEYS。", 503
        )
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ServiceError("unauthorized", "请提供 Authorization: Bearer <api_key>。", 401)
    token = token.strip()
    for key, tenant_id in keys.items():
        if hmac.compare_digest(key, token):
            principal = Principal(tenant_id=tenant_id, subject=f"tenant:{tenant_id}")
            tenant_id_var.set(principal.tenant_id)
            return principal
    raise ServiceError("unauthorized", "API Key 无效。", 401)


PrincipalDep = Annotated[Principal, Depends(require_principal)]
