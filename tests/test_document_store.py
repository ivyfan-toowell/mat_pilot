"""验证文献 SSOT：无数据库时写本地 JSON；有 store 时索引不再保存全文副本。"""

from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import Settings
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.retrieval import Chunk
from app.services.document_service import DocumentService
from app.services.vector_store import VectorStore


def test_document_service_with_store_does_not_fall_back_to_json(workspace_dir, monkeypatch):
    from app.core.errors import ServiceError

    settings = Settings(_env_file=None, database_url="postgresql://fixture")
    service = DocumentService(workspace_dir, settings, tenant_id="local")
    document_id = uuid4()
    folder = service.directory / str(document_id)
    folder.mkdir(parents=True)
    stale = ParsedDocument(
        document_id=document_id,
        filename="stale.pdf",
        title="stale-on-disk",
        sha256="0" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[],
    )
    (folder / "parsed.json").write_text(stale.model_dump_json(), encoding="utf-8")

    class MissingStore:
        def get(self, _document_id):
            raise ServiceError("document_not_found", "missing", 404)

    service.store = MissingStore()
    try:
        service.load(document_id)
        raise AssertionError("expected document_not_found")
    except ServiceError as exc:
        assert exc.code == "document_not_found"


def test_document_service_without_db_keeps_local_json(workspace_dir):
    service = DocumentService(workspace_dir, Settings(_env_file=None, database_url=None))
    # Minimal path: persist helper via private API with a parsed fixture.
    document = ParsedDocument(
        document_id=uuid4(),
        filename="fixture.pdf",
        title="local-ssot",
        sha256="0" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[],
    )
    folder = service.directory / str(document.document_id)
    folder.mkdir(parents=True)
    service._persist_document(document, folder)
    assert (folder / "parsed.json").is_file()
    assert service.load(document.document_id).title == "local-ssot"


def test_vector_replace_stores_index_stub_not_full_document(monkeypatch):
    settings = Settings(
        _env_file=None, database_url="postgresql://fixture", embedding_dimensions=64
    )
    store = VectorStore(settings, "local")
    document = ParsedDocument(
        document_id=uuid4(),
        filename="fixture.pdf",
        title="should-not-copy-blocks",
        sha256="0" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[
            SourceBlock(
                block_id="b1",
                page_number=1,
                kind="text",
                bbox=(0, 0, 1, 1),
                text="secret evidence",
                raw_text="secret evidence",
            )
        ],
    )
    chunk = Chunk(
        chunk_id=uuid4(),
        document_id=document.document_id,
        block_id="b1",
        page_number=1,
        kind="text",
        text="secret evidence",
        title=document.title,
    )
    captured = {}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            captured.setdefault("sql", []).append((sql, params))
            if "SELECT tenant_id" in sql:
                return type("R", (), {"fetchone": lambda self: None})()
            return type("R", (), {"fetchone": lambda self: None, "fetchall": lambda self: []})()

        def cursor(self):
            return self

        def executemany(self, sql, seq):
            captured["chunks"] = list(seq)

    monkeypatch.setattr(store, "verify_embedding_config", lambda: None)
    monkeypatch.setattr(store, "connect", lambda: FakeConn())
    store.replace(document, [chunk], [[0.0] * 64])
    insert = next(
        params
        for sql, params in captured["sql"]
        if params and len(params) >= 2 and "Jsonb" in type(params[1]).__name__
    )
    payload = getattr(insert[1], "obj", None) or getattr(insert[1], "adapted", None) or insert[1]
    if hasattr(payload, "obj"):
        payload = payload.obj
    assert payload["source"] == "index_registry"
    assert "secret evidence" not in str(payload)
