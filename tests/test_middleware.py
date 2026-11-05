"""验证 request_id、限流与错误体审计字段。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.middleware import RateLimitMiddleware, _TokenBucket
from app.main import app


@pytest.mark.api
def test_response_includes_request_id(workspace_dir):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, data_dir=workspace_dir, database_url=None, rate_limit_per_minute=0
    )
    try:
        with TestClient(app) as client:
            response = client.get("/health", headers={"X-Request-ID": "fixture-req-1"})
            assert response.status_code == 200
            assert response.headers.get("X-Request-ID") == "fixture-req-1"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_service_error_includes_request_id(workspace_dir):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        auth_mode="api_key",
        auth_api_keys="t:secret",
        rate_limit_per_minute=0,
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/documents", headers={"X-Request-ID": "err-1"})
            assert response.status_code == 401
            body = response.json()["error"]
            assert body["request_id"] == "err-1"
            assert response.headers.get("X-Request-ID") == "err-1"
    finally:
        app.dependency_overrides.clear()


def test_token_bucket_exhausts():
    bucket = _TokenBucket(2)
    assert bucket.allow() and bucket.allow()
    assert not bucket.allow()


@pytest.mark.api
def test_rate_limit_middleware_can_block(workspace_dir):
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        rate_limit_per_minute=1,
        rate_limit_costly_per_minute=1,
    )
    limiter = RateLimitMiddleware(app, settings)
    assert limiter.global_bucket.allow()
    assert not limiter.global_bucket.allow()


def test_rate_limit_response_includes_request_id(workspace_dir):
    import json

    from app.core.request_context import request_id_var

    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        rate_limit_per_minute=1,
        rate_limit_costly_per_minute=1,
    )
    limiter = RateLimitMiddleware(app, settings)
    request_id_var.set("rate-req-1")
    response = limiter._rate_limited("rate_limited", "请求过于频繁，请稍后再试。")
    assert response.status_code == 429
    payload = json.loads(response.body)
    assert payload["error"]["request_id"] == "rate-req-1"
    assert response.headers["X-Request-ID"] == "rate-req-1"
