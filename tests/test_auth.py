"""验证 API Key 认证与租户文件隔离。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings, tenant_data_dir
from app.main import app
from app.schemas.document import ParsedDocument


def _client(settings: Settings) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _save_document(root, title="tenant-a"):
    document = ParsedDocument(
        document_id=uuid4(),
        filename="fixture.pdf",
        title=title,
        sha256="0" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[],
    )
    folder = root / "documents" / str(document.document_id)
    folder.mkdir(parents=True)
    (folder / "parsed.json").write_text(document.model_dump_json(), encoding="utf-8")
    return document


@pytest.mark.api
def test_api_key_mode_requires_bearer(workspace_dir):
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        auth_mode="api_key",
        auth_api_keys="alpha:secret-a,beta:secret-b",
    )
    try:
        with _client(settings) as client:
            assert client.get("/api/v1/documents").status_code == 401
            assert client.get("/health").status_code == 200
            ok = client.get("/api/v1/documents", headers={"Authorization": "Bearer secret-a"})
            assert ok.status_code == 200
            assert ok.json() == []
            bad = client.get("/api/v1/documents", headers={"Authorization": "Bearer wrong"})
            assert bad.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_tenants_cannot_read_each_others_documents(workspace_dir):
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        auth_mode="api_key",
        auth_api_keys="alpha:secret-a,beta:secret-b",
    )
    document = _save_document(tenant_data_dir(settings, "alpha"))
    try:
        with _client(settings) as client:
            owned = client.get(
                f"/api/v1/documents/{document.document_id}",
                headers={"Authorization": "Bearer secret-a"},
            )
            assert owned.status_code == 200
            denied = client.get(
                f"/api/v1/documents/{document.document_id}",
                headers={"Authorization": "Bearer secret-b"},
            )
            assert denied.status_code == 404
            listed = client.get("/api/v1/documents", headers={"Authorization": "Bearer secret-b"})
            assert listed.status_code == 200
            assert listed.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_auth_off_uses_local_tenant_root(workspace_dir):
    settings = Settings(
        _env_file=None, data_dir=workspace_dir, database_url=None, auth_mode="off"
    )
    document = _save_document(tenant_data_dir(settings, "local"))
    try:
        with _client(settings) as client:
            response = client.get("/api/v1/documents")
            assert response.status_code == 200
            assert response.json()[0]["document_id"] == str(document.document_id)
    finally:
        app.dependency_overrides.clear()
