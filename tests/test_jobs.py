"""验证异步任务提交、轮询、失败落盘与租户隔离。"""

import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.research import ResearchAgent
from app.core.config import Settings, get_settings, tenant_data_dir
from app.core.errors import ServiceError
from app.main import app
from app.schemas.agent import AgentResult
from app.services.job_service import JobStore


def _wait(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


@pytest.mark.api
def test_agent_job_returns_202_and_result(workspace_dir, monkeypatch):
    settings = Settings(_env_file=None, data_dir=workspace_dir, job_workers=1)
    app.dependency_overrides[get_settings] = lambda: settings

    def run(self, request, routing_reason=None):
        return AgentResult(
            run_id=uuid4(),
            created_at=datetime.now(UTC),
            question=request.question,
            status="answered",
            answer="async fixture",
            tools=[],
            model_steps=1,
            routing_reason=routing_reason,
        )

    monkeypatch.setattr(ResearchAgent, "run", run)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/jobs/agent", json={"question": "fixture question"})
            assert response.status_code == 202
            body = response.json()
            assert body["status"] == "queued" and body["kind"] == "agent_run"
            job = _wait(client, body["job_id"])
            assert job["status"] == "succeeded"
            assert job["result"]["answer"] == "async fixture"
            assert JobStore(tenant_data_dir(settings, "local")).load(body["job_id"]).status == (
                "succeeded"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_failed_job_persists_service_error(workspace_dir, monkeypatch):
    settings = Settings(_env_file=None, data_dir=workspace_dir, job_workers=1)
    app.dependency_overrides[get_settings] = lambda: settings

    def run(self, request, routing_reason=None):
        raise ServiceError("database_unavailable", "fixture unavailable", 503)

    monkeypatch.setattr(ResearchAgent, "run", run)
    try:
        with TestClient(app) as client:
            job_id = client.post(
                "/api/v1/jobs/agent", json={"question": "fixture question"}
            ).json()["job_id"]
            job = _wait(client, job_id)
            assert job["status"] == "failed"
            assert job["error"]["code"] == "database_unavailable"
            assert job["result"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_jobs_are_tenant_scoped(workspace_dir, monkeypatch):
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        auth_mode="api_key",
        auth_api_keys="alpha:secret-a,beta:secret-b",
        job_workers=1,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    def run(self, request, routing_reason=None):
        return AgentResult(
            run_id=uuid4(),
            created_at=datetime.now(UTC),
            question=request.question,
            status="answered",
            answer="owned",
            tools=[],
            model_steps=0,
        )

    monkeypatch.setattr(ResearchAgent, "run", run)
    headers_a = {"Authorization": "Bearer secret-a"}
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/jobs/agent", json={"question": "tenant a"}, headers=headers_a
            )
            assert created.status_code == 202
            job_id = created.json()["job_id"]
            deadline = time.monotonic() + 5
            owned = None
            while time.monotonic() < deadline:
                owned = client.get(f"/api/v1/jobs/{job_id}", headers=headers_a)
                assert owned.status_code == 200
                if owned.json()["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.05)
            assert owned is not None and owned.json()["status"] == "succeeded"
            denied = client.get(
                f"/api/v1/jobs/{job_id}", headers={"Authorization": "Bearer secret-b"}
            )
            assert denied.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_index_job_requires_existing_document(workspace_dir):
    settings = Settings(_env_file=None, data_dir=workspace_dir, job_workers=1)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            job_id = client.post(
                "/api/v1/jobs/knowledge/index", json={"document_id": str(uuid4())}
            ).json()["job_id"]
            job = _wait(client, job_id)
            assert job["status"] == "failed"
            assert job["error"]["code"] == "document_not_found"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_sync_agent_endpoint_still_works(workspace_dir, monkeypatch):
    settings = Settings(_env_file=None, data_dir=workspace_dir)
    app.dependency_overrides[get_settings] = lambda: settings

    def run(self, request, routing_reason=None):
        return AgentResult(
            run_id=uuid4(),
            created_at=datetime.now(UTC),
            question=request.question,
            status="answered",
            answer="sync fixture",
            tools=[],
            model_steps=1,
        )

    monkeypatch.setattr(ResearchAgent, "run", run)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/agent/run", json={"question": "sync path"})
            assert response.status_code == 200
            assert response.json()["answer"] == "sync fixture"
    finally:
        app.dependency_overrides.clear()


def test_job_store_roundtrip(workspace_dir):
    store = JobStore(workspace_dir)
    job = store.create("local", "experiment_extract", {"document_id": str(uuid4())})
    loaded = store.load(job.job_id)
    assert loaded.status == "queued" and loaded.kind == "experiment_extract"
    assert store.load(job.job_id).job_id == job.job_id
