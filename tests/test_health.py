from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import app
from app.services.vector_store import VectorStore


def test_liveness_does_not_claim_database_readiness():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            response = client.get("/health/ready")
            assert response.status_code == 503
            assert response.json()["checks"]["database"] == "database_not_configured"
    finally:
        app.dependency_overrides.clear()


def test_readiness_checks_database_without_returning_credentials(monkeypatch):
    settings = Settings(
        _env_file=None, dashscope_api_key="fixture-private-llm", mp_api_key="fixture-private-mp"
    )

    class Connection:
        def execute(self, query):
            assert query == "SELECT 1"

    @contextmanager
    def connect(*args):
        yield Connection()

    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(VectorStore, "connect", connect)
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
            assert response.status_code == 200
            assert "fixture-private" not in response.text
            monkeypatch.setattr(
                VectorStore,
                "connect",
                lambda *args: (_ for _ in ()).throw(
                    ServiceError("database_unavailable", "fixture", 503)
                ),
            )
            assert client.get("/health/ready").status_code == 503
    finally:
        app.dependency_overrides.clear()
