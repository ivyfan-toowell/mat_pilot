"""Bounded paper selection, complete pagination and recoverable tenant-scoped deletion."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.core.config import Settings, get_settings, tenant_data_dir
from app.core.errors import ServiceError
from app.main import app
from app.schemas.document import ParsedDocument
from app.services.catalog_service import document_page, list_documents
from app.services.document_service import DocumentService
from app.services.document_store import DocumentStore
from ui import document_catalog_page, shared


def _save(root, index=0, **values):
    doc = ParsedDocument(
        document_id=uuid4(),
        filename=f"paper-{index}.pdf",
        title=f"论文 {index}",
        authors=[f"作者 {index}"],
        sha256="a" * 64,
        page_count=1,
        parsed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
        blocks=[],
    ).model_copy(update=values)
    folder = root / "documents" / str(doc.document_id)
    folder.mkdir(parents=True)
    (folder / "original.pdf").write_bytes(b"original fixture")
    (folder / "parsed.json").write_text(doc.model_dump_json(), encoding="utf-8")
    (folder / "experiments.json").write_text('{"reviews":"keep"}', encoding="utf-8")
    return doc


def test_local_catalog_pages_all_records_and_searches_authors(workspace_dir):
    docs = [_save(workspace_dir, index) for index in range(23)]
    first = document_page(workspace_dir, limit=10)
    second = document_page(workspace_dir, limit=10, offset=10)
    final = document_page(workspace_dir, limit=10, offset=20)
    assert first.total == second.total == final.total == 23
    assert [item.document_id for item in first.items] == [
        doc.document_id for doc in docs[::-1][:10]
    ]
    assert len(second.items) == 10 and len(final.items) == 3
    assert len({item.document_id for page in (first, second, final) for item in page.items}) == 23
    assert (
        document_page(workspace_dir, query="作者 22").items[0].document_id == docs[22].document_id
    )
    assert document_page(workspace_dir, query="paper-20.pdf").total == 1
    assert document_page(workspace_dir, query="不存在").total == 0


def test_local_delete_restore_keeps_other_versions_original_and_reviews(workspace_dir):
    original = _save(workspace_dir)
    sibling = _save(workspace_dir, 1, parent_document_id=original.document_id)
    service = DocumentService(workspace_dir)
    deleted = service.set_deleted(original.document_id, deleted=True)
    assert deleted.deleted_at is not None
    with pytest.raises(ServiceError) as caught:
        service.load(original.document_id)
    assert caught.value.status_code == 404
    assert [item.document_id for item in list_documents(workspace_dir)] == [sibling.document_id]
    assert document_page(workspace_dir, deleted=True).items[0].document_id == original.document_id
    folder = service.directory / str(original.document_id)
    assert (folder / "original.pdf").read_bytes() == b"original fixture"
    assert (folder / "experiments.json").read_text(encoding="utf-8") == '{"reviews":"keep"}'
    assert service.set_deleted(original.document_id, deleted=True).deleted_at == deleted.deleted_at
    restored = service.set_deleted(original.document_id, deleted=False)
    assert restored == original
    assert document_page(workspace_dir, deleted=True).total == 0
    assert len(list_documents(workspace_dir)) == 2


@pytest.mark.api
def test_management_api_limits_and_tenant_isolation(workspace_dir):
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        auth_mode="api_key",
        auth_api_keys="alpha:secret-a,beta:secret-b",
    )
    original = _save(tenant_data_dir(settings, "alpha"))
    endpoint = f"/api/v1/documents/{original.document_id}"
    headers = {"Authorization": "Bearer secret-a"}
    other = {"Authorization": "Bearer secret-b"}
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            assert client.delete(endpoint).status_code == 401
            assert client.delete(endpoint, headers=other).status_code == 404
            assert client.post(endpoint + "/restore", headers=other).status_code == 404
            for query in ("limit=0", "limit=101", "offset=-1"):
                assert (
                    client.get("/api/v1/documents/catalog?" + query, headers=headers).status_code
                    == 422
                )
            assert client.get("/api/v1/documents/catalog", headers=other).json()["total"] == 0
            assert client.delete(endpoint, headers=headers).json()["deleted_at"]
            assert client.get("/api/v1/documents?limit=10", headers=headers).json() == []
            assert client.get(endpoint, headers=headers).status_code == 404
            trash = client.get("/api/v1/documents/catalog?deleted=true", headers=headers).json()
            assert trash["total"] == 1 and trash["items"][0]["document_id"] == str(
                original.document_id
            )
            assert client.post(endpoint + "/restore", headers=headers).json()["deleted_at"] is None
            assert client.get(endpoint, headers=headers).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_database_catalog_and_delete_are_tenant_scoped(monkeypatch):
    document = _save_fixture_model()
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))
            if "count(*)" in sql:
                return type("Result", (), {"fetchone": lambda _: {"total": 11}})()
            if "RETURNING parsed" in sql:
                updated = {**document.model_dump(mode="json"), **params[0].obj}
                return type(
                    "Result",
                    (),
                    {
                        "fetchone": lambda _: {
                            "parsed": updated,
                        }
                    },
                )()
            return type(
                "Result",
                (),
                {
                    "fetchall": lambda _: [
                        {
                            "parsed": document.model_dump(mode="json"),
                            "has_experiments": True,
                        }
                    ]
                },
            )()

    store = DocumentStore(Settings(_env_file=None, database_url=None), "alpha")
    monkeypatch.setattr(store, "connect", Connection)
    page = store.page(limit=10, offset=10, query="作者", deleted=False)
    assert page.total == 11 and page.offset == 10 and page.items[0].has_experiments
    assert calls[0][1] == ("alpha", False, "作者", "作者")
    assert calls[1][1][-2:] == (10, 10)
    assert all("tenant_id=%s" in sql and "deleted_at" in sql for sql, _ in calls)
    deleted = store.set_deleted(document.document_id, datetime.now(UTC))
    assert deleted.deleted_at and deleted.document_id == document.document_id
    assert calls[-1][1][-1] == "alpha" and "DELETE FROM" not in calls[-1][0]


def _save_fixture_model(index=0):
    return ParsedDocument(
        document_id=uuid4(),
        filename=f"paper-{index}.pdf",
        title=f"论文 {index}",
        authors=["作者"],
        sha256="a" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[],
    )


class _GetJson:
    def __init__(self, items):
        self.items = items
        self.requests = []

    def __call__(self, backend, path):
        self.requests.append(path)
        if path == "/api/v1/documents?limit=10":
            return [item for item in self.items if not item.get("deleted_at")][:10]
        if path.startswith("/api/v1/documents/catalog?"):
            query = parse_qs(urlsplit(path).query)
            deleted = query["deleted"][0] == "true"
            items = [item for item in self.items if bool(item.get("deleted_at")) == deleted]
            search = query.get("q", [""])[0]
            items = [item for item in items if search in item["title"] or not search]
            offset = int(query["offset"][0])
            return {
                "items": items[offset : offset + 10],
                "total": len(items),
                "limit": 10,
                "offset": offset,
            }
        for item in self.items:
            if path.endswith(item["document_id"]):
                if item.get("deleted_at"):
                    break
                return item
        raise httpx.HTTPStatusError(
            "missing", request=httpx.Request("GET", backend), response=httpx.Response(404)
        )

    def clear(self):
        pass


def _items(count):
    return [
        {**_save_fixture_model(index).model_dump(mode="json"), "has_experiments": False}
        for index in range(count)
    ]


def test_recent_picker_limits_ten_and_keeps_a_paper_opened_from_catalog(monkeypatch):
    items = _items(15)
    get = _GetJson(items)
    monkeypatch.setattr(shared, "get_json", get)
    documents = shared.recent_documents("http://fixture", items[14]["document_id"])
    assert len(documents) == 10 and documents[-1]["document_id"] == items[14]["document_id"]
    items[14]["deleted_at"] = "2026-11-11T00:00:00Z"
    assert all(
        item["document_id"] != items[14]["document_id"]
        for item in shared.recent_documents("http://fixture", items[14]["document_id"])
    )


def test_catalog_ui_pagination_search_and_open(monkeypatch):
    items = _items(23)
    get = _GetJson(items)
    monkeypatch.setattr(document_catalog_page, "get_json", get)
    page = AppTest.from_string(
        "from ui.document_catalog_page import render\nrender('http://fixture')"
    ).run()
    assert not page.exception
    assert len([button for button in page.button if button.label == "打开"]) == 10
    next(button for button in page.button if button.label == "下一页").click().run()
    assert "offset=10" in get.requests[-1]
    page.text_input(key="document_catalog_query").input("论文 22").run()
    assert "offset=0" in get.requests[-1]
    assert len([button for button in page.button if button.label == "打开"]) == 1
    page.button(key=f"open_paper_{items[22]['document_id']}").click().run()
    assert page.session_state["pending_document_id"] == items[22]["document_id"]
    assert page.session_state["workspace"] == "论文解析"


def test_catalog_ui_delete_requires_confirmation_and_can_restore(monkeypatch):
    items = _items(1)
    get = _GetJson(items)
    monkeypatch.setattr(document_catalog_page, "get_json", get)
    deleted = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def delete(self, url):
            deleted.append(url)
            items[0]["deleted_at"] = "2026-11-11T00:00:00Z"
            return httpx.Response(200, request=httpx.Request("DELETE", url))

        def post(self, url):
            items[0]["deleted_at"] = None
            return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(document_catalog_page.httpx, "Client", Client)
    page = AppTest.from_string(
        "from ui.document_catalog_page import render\nrender('http://fixture')"
    )
    document_id = items[0]["document_id"]
    page.session_state["active_document_id"] = document_id
    page.run()
    page.button(key=f"delete_paper_{document_id}").click().run()
    assert not deleted
    page.button(key=f"cancel_delete_{document_id}").click().run()
    assert not deleted
    page.button(key=f"delete_paper_{document_id}").click().run()
    page.button(key=f"confirm_delete_{document_id}").click().run()
    assert not page.exception and len(deleted) == 1
    assert "active_document_id" not in page.session_state
    page.radio(key="document_catalog_scope").set_value("回收站").run()
    page.button(key=f"restore_paper_{document_id}").click().run()
    assert not page.exception and items[0]["deleted_at"] is None
