"""Bibliography edits preserve evidence, versions and tenant isolation."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.core.config import Settings, get_settings, tenant_data_dir
from app.ingestion.bibliography import _matching_title, read_bibliography
from app.ingestion.pdf_parser import parse_pdf
from app.main import app
from app.schemas.document import DocumentMetadataUpdate, ParsedDocument, SourceBlock
from app.services.document_service import DocumentService
from app.services.document_store import DocumentStore
from ui import document_page, shared


def _pdf():
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 100), "Optical properties of annealed titanium dioxide")
        pdf.set_metadata({"author": "Danqi Li, Hongchen Song and Xia Meng"})
        return pdf.tobytes()


def _document():
    return ParsedDocument(
        document_id=uuid4(),
        filename="paper.pdf",
        title="旧标题",
        sha256="a" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[
            SourceBlock(
                block_id="p1-source",
                page_number=1,
                kind="text",
                bbox=(10, 10, 100, 100),
                text="氮气退火对二氧化钛薄膜光学性能的影响*\n居勇峰,祖小涛,向 霞\n(电子科技大学)",
                raw_text="原文不可修改",
            )
        ],
    )


def test_bibliography_reads_author_metadata_and_grounded_filename(workspace_dir):
    path = workspace_dir / "paper.pdf"
    path.write_bytes(_pdf())
    document = _document().model_copy(
        update={
            "filename": "Optical properties of annealed titanium dioxide.pdf",
        }
    )
    title, authors = read_bibliography(path, document)
    assert title == "Optical properties of annealed titanium dioxide"
    assert authors == ["Danqi Li", "Hongchen Song", "Xia Meng"]


def test_chinese_byline_and_unknown_author_are_not_prose(workspace_dir):
    path = workspace_dir / "paper.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        path.write_bytes(pdf.tobytes())
    document = _document().model_copy(
        update={
            "title": "氮气退火对二氧化钛薄膜光学性能的影响*",
        }
    )
    title, authors = read_bibliography(path, document)
    assert title == document.title.rstrip("*")
    assert authors == ["居勇峰", "祖小涛", "向霞"]
    document.blocks[0].text = title + "\n(电子科技大学应用物理系)\n摘要:实验研究"
    assert read_bibliography(path, document)[1] == []
    document.filename = "文件名中编造的论文标题.pdf"
    assert read_bibliography(path, document)[0] == title
    assert _matching_title(title + "\n\ue012", title) == title


def test_metadata_edit_preserves_identity_sources_and_experiments(workspace_dir):
    service = DocumentService(workspace_dir)
    original = _pdf()
    document = service.ingest(original, "paper.pdf")
    folder = service.directory / str(document.document_id)
    (folder / "experiments.json").write_text('{"keep":"reviewed"}', encoding="utf-8")
    updated = service.update_metadata(
        document.document_id,
        DocumentMetadataUpdate(
            title="  正确论文标题  ",
            authors=[" 作者甲 ", "作者乙", "作者甲", ""],
        ),
    )
    assert updated.title == "正确论文标题"
    assert updated.authors == ["作者甲", "作者乙"]
    assert updated.metadata_edited
    assert service.refresh_bibliography(document.document_id) == updated
    assert service.load(document.document_id) == updated
    assert updated.blocks == document.blocks
    assert updated.sha256 == document.sha256 and updated.parsed_at == document.parsed_at
    assert (folder / "original.pdf").read_bytes() == original
    assert (folder / "experiments.json").read_text(encoding="utf-8") == '{"keep":"reviewed"}'


def test_reparse_inherits_manually_corrected_metadata(workspace_dir, monkeypatch):
    service = DocumentService(
        workspace_dir,
        Settings(
            _env_file=None,
            database_url=None,
            mineru_cli_path=workspace_dir / "mineru.exe",
        ),
    )
    original = service.ingest(_pdf(), "paper.pdf")
    service.update_metadata(
        original.document_id,
        DocumentMetadataUpdate(
            title="人工核对的论文标题",
            authors=["作者甲"],
        ),
    )

    def fake_parse(path, document_id, filename, *_):
        return parse_pdf(path, document_id, filename).model_copy(update={"parser_engine": "mineru"})

    monkeypatch.setattr("app.services.document_service.parse_mineru", fake_parse)
    updated = service.reparse_with_mineru(original.document_id)
    assert updated.title == "人工核对的论文标题" and updated.authors == ["作者甲"]
    assert updated.metadata_edited and updated.parent_document_id == original.document_id
    assert updated.document_id != original.document_id


@pytest.mark.api
def test_metadata_api_validates_fields_and_enforces_tenant(workspace_dir):
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        auth_mode="api_key",
        auth_api_keys="alpha:secret-a,beta:secret-b",
    )
    service = DocumentService(tenant_data_dir(settings, "alpha"))
    document = service.ingest(_pdf(), "paper.pdf")
    endpoint = f"/api/v1/documents/{document.document_id}/metadata"
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer secret-a"}
            assert client.patch(endpoint, json={"title": "新标题"}).status_code == 401
            assert (
                client.patch(
                    endpoint,
                    json={"title": "新标题"},
                    headers={
                        "Authorization": "Bearer secret-b",
                    },
                ).status_code
                == 404
            )
            for invalid in ({"title": " "}, {"title": "x", "blocks": []}):
                assert client.patch(endpoint, json=invalid, headers=headers).status_code == 422
            response = client.patch(
                endpoint,
                json={
                    "title": "新标题",
                    "authors": ["作者甲", "作者乙"],
                },
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["blocks"] == document.model_dump(mode="json")["blocks"]
            listing = client.get("/api/v1/documents", headers=headers).json()[0]
            assert listing["authors"] == ["作者甲", "作者乙"]
            assert listing["title"] == "新标题"
    finally:
        app.dependency_overrides.clear()


def test_database_metadata_edit_is_scoped_and_updates_citation_titles(monkeypatch):
    document = _document()
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))
            if "RETURNING parsed" in sql:
                updated = document.model_copy(update=params[0].obj)
                return type(
                    "Result",
                    (),
                    {
                        "fetchone": lambda _: {
                            "parsed": updated.model_dump(mode="json"),
                        }
                    },
                )()

    store = DocumentStore(Settings(_env_file=None, database_url=None), "alpha")
    monkeypatch.setattr(store, "connect", Connection)
    updated = store.update_metadata(
        document.document_id,
        DocumentMetadataUpdate(
            title="新标题",
            authors=["作者甲"],
        ),
    )
    assert updated.title == "新标题" and updated.blocks == document.blocks
    assert len(calls) == 3
    assert all("tenant_id=%s" in sql and params[-1] == "alpha" for sql, params in calls)
    assert "UPDATE mp_chunks SET title" in calls[1][0]


def test_document_labels_are_readable_and_distinguish_versions():
    document = _document().model_dump(mode="json")
    document["authors"] = ["居勇峰", "祖小涛", "向霞"]
    label = shared.document_label(document)
    assert label.startswith("居勇峰 等 · 旧标题")
    assert shared.document_label({**document, "document_id": str(uuid4())}) != label
    assert "作者待补充" in shared.document_label({**document, "authors": []})


def test_metadata_editor_saves_and_refreshes_catalog(monkeypatch):
    document = _document().model_dump(mode="json")
    document["warnings"] = []
    catalog = [{**document, "has_experiments": False}]
    monkeypatch.setattr(shared, "service_status", lambda _: {"status": "ready"})

    class GetJson:
        def __call__(self, backend, path):
            if path.endswith("/experiments"):
                raise httpx.HTTPStatusError(
                    "missing", request=httpx.Request("GET", backend), response=httpx.Response(404)
                )
            return catalog if path == "/api/v1/documents?limit=10" else document

        def clear(self):
            pass

    get = GetJson()
    monkeypatch.setattr(shared, "get_json", get)
    monkeypatch.setattr(document_page, "get_json", get)
    saved = []

    def patch(url, **kwargs):
        saved.append(kwargs["json"])
        document.update(kwargs["json"])
        catalog[0].update(kwargs["json"])
        return httpx.Response(200, json=document, request=httpx.Request("PATCH", url))

    monkeypatch.setattr(httpx, "patch", patch)
    page = AppTest.from_string("from ui.document_page import render\nrender('http://fixture')")
    page.session_state["active_document_id"] = document["document_id"]
    page.run()
    assert not page.exception
    next(field for field in page.text_input if field.label == "论文标题").input("校正后的论文标题")
    next(field for field in page.text_area if field.label.startswith("论文作者")).input(
        "居勇峰\n祖小涛"
    )
    next(button for button in page.button if button.label == "保存论文信息").click().run()
    assert not page.exception
    assert saved == [{"title": "校正后的论文标题", "authors": ["居勇峰", "祖小涛"]}]
    assert "居勇峰" in str(page.selectbox(key="active_document_id").options)
