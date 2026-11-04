"""验证文献目录、历史任务及实验记录回读，不将合成记录作为科研验收数据。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.schemas.agent import AgentResult
from app.schemas.document import ParsedDocument
from app.schemas.experiment import ExtractionResult


def save_document(root, offset=0):
    document = ParsedDocument(
        document_id=uuid4(),
        filename="fixture.pdf",
        title="目录测试，不作为科研证据",
        sha256="0" * 64,
        page_count=1,
        parsed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=offset),
        blocks=[],
    )
    folder = root / "documents" / str(document.document_id)
    folder.mkdir(parents=True)
    (folder / "parsed.json").write_text(document.model_dump_json(), encoding="utf-8")
    return document, folder


@pytest.fixture
def catalog_client(workspace_dir):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, data_dir=workspace_dir
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_document_catalog_is_bounded_sorted_and_omits_full_evidence(workspace_dir, catalog_client):
    old, _ = save_document(workspace_dir)
    new, folder = save_document(workspace_dir, 1)
    (folder / "experiments.json").write_text("{}", encoding="utf-8")
    corrupt = workspace_dir / "documents" / str(uuid4())
    corrupt.mkdir()
    (corrupt / "parsed.json").write_text("invalid", encoding="utf-8")
    mismatch = workspace_dir / "documents" / str(uuid4())
    mismatch.mkdir()
    (mismatch / "parsed.json").write_text(old.model_dump_json(), encoding="utf-8")
    response = catalog_client.get("/api/documents")
    assert response.status_code == 200
    records = response.json()
    assert [item["document_id"] for item in records] == [str(new.document_id), str(old.document_id)]
    assert records[0]["has_experiments"]
    assert "blocks" not in records[0] and "sha256" not in records[0]
    assert len(catalog_client.get("/api/documents?limit=1").json()) == 1
    assert catalog_client.get("/api/documents?limit=0").status_code == 422


@pytest.mark.api
def test_saved_experiments_are_read_without_model_execution(
    workspace_dir, catalog_client, monkeypatch
):
    document, folder = save_document(workspace_dir)
    extraction = ExtractionResult(
        document_id=document.document_id,
        model="test-fixture",
        experiments=[],
        rejected=[],
        context_truncated=False,
    )
    (folder / "experiments.json").write_text(extraction.model_dump_json(), encoding="utf-8")

    def fail(*args, **kwargs):
        pytest.fail("回读已保存记录不能重新调用提取模型")

    monkeypatch.setattr("app.api.documents.ExperimentExtractor.extract", fail)
    response = catalog_client.get(f"/api/documents/{document.document_id}/experiments")
    assert response.status_code == 200
    assert response.json() == extraction.model_dump(mode="json")
    assert catalog_client.get(f"/api/documents/{uuid4()}/experiments").status_code == 404


@pytest.mark.api
def test_history_only_lists_final_matching_runs(workspace_dir, catalog_client):
    folder = workspace_dir / "agent_runs"
    folder.mkdir()
    result = AgentResult(
        run_id=uuid4(),
        created_at=datetime.now(UTC),
        question="归档测试任务",
        status="insufficient_evidence",
        answer="合成测试记录，不作为科研证据。",
        tools=[],
        model_steps=0,
    )
    payload = result.model_dump_json()
    (folder / f"{result.run_id}.json").write_text(payload, encoding="utf-8")
    (folder / f"{result.run_id}.candidate.json").write_text(payload, encoding="utf-8")
    (folder / f"{uuid4()}.json").write_text(payload, encoding="utf-8")
    (folder / f"{uuid4()}.failure.json").write_text('{"error":"fixture"}', encoding="utf-8")
    response = catalog_client.get("/api/agent/runs")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["run_id"] == str(result.run_id)
    assert "tools" not in response.json()[0] and "claims" not in response.json()[0]
    assert catalog_client.get("/api/agent/runs?limit=101").status_code == 422
