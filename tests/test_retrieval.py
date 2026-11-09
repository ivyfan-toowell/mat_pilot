"""Retrieval contract tests; no fabricated fixtures are used as acceptance evidence."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.ingestion.chunker import chunk_document
from app.main import app
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.retrieval import AnswerDraft, SearchHit, SearchResult
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RagService, validate_answer


def paper():
    return ParsedDocument(
        document_id=uuid4(),
        filename="test.pdf",
        title="fixture",
        sha256="0" * 64,
        page_count=2,
        parsed_at=datetime.now(UTC),
        blocks=[
            SourceBlock(
                block_id="p1-text",
                page_number=1,
                kind="text",
                bbox=(0, 0, 1, 1),
                text="abcdefghij" * 10,
                raw_text="",
            ),
            SourceBlock(
                block_id="p2-table",
                page_number=2,
                kind="table",
                bbox=(0, 0, 1, 1),
                text="header\n" + "row\n" * 40,
                raw_text="",
            ),
        ],
    )


def test_chunk_identity_page_overlap_and_intact_table():
    document = paper()
    chunks = chunk_document(document, size=50, overlap=10)
    assert chunks == chunk_document(document, size=50, overlap=10)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    # V0.10 adds source markers before each paragraph; overlap applies to
    # original text, not to the provenance marker itself.
    assert chunks[0].text[-10:] == chunks[1].text.split("\n", 1)[1][:10]
    assert chunks[-1].text.endswith(document.blocks[-1].text.strip())
    assert chunks[-1].source_block_ids == ["p2-table"]
    assert chunks[-1].page_number == 2 and chunks[0].page_number == 1
    assert all(chunk.document_id == document.document_id for chunk in chunks)
    with pytest.raises(ValueError):
        chunk_document(document, size=10, overlap=10)


def test_embedding_batch_order_dimension_and_request(monkeypatch):
    settings = Settings(_env_file=None, dashscope_api_key="fixture", embedding_dimensions=64)
    sizes = []

    def post(self, url, *, json, headers):
        sizes.append(len(json["input"]))
        assert json["dimensions"] == 64 and url.endswith("/embeddings")
        data = [
            {"index": i, "embedding": [float(i + 1)] * 64}
            for i in reversed(range(len(json["input"])))
        ]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", post)
    result = EmbeddingService(settings).embed(["test"] * 12)
    assert sizes == [10, 2] and len(result) == 12
    assert result[0][0] == 1 and result[9][0] == 10


@pytest.mark.parametrize("vector", [[0] * 64, [1] * 63, [float("nan")] * 64])
def test_embedding_rejects_invalid_vector(monkeypatch, vector):
    settings = Settings(_env_file=None, dashscope_api_key="fixture", embedding_dimensions=64)

    def post(self, url, **kwargs):
        # use direct response bytes to exercise non-finite provider data as well
        import json

        return httpx.Response(
            200,
            content=json.dumps({"data": [{"index": 0, "embedding": vector}]}),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(ServiceError) as caught:
        EmbeddingService(settings).embed(["test"])
    assert caught.value.code == "embedding_failed"


def search_result():
    hit = SearchHit(**chunk_document(paper())[0].model_dump(), similarity=0.8)
    hit.text = "Synthetic test evidence, not a scientific measurement."
    return SearchResult(question="fixture?", hits=[hit], embedding_model="test")


@pytest.mark.parametrize("source_id,quote", [(2, "Synthetic"), (1, "invented evidence")])
def test_rejects_invented_citation_and_quote(source_id, quote):
    draft = AnswerDraft.model_validate(
        {
            "claims": [
                {"text": "test claim", "citations": [{"source_id": source_id, "quote": quote}]}
            ]
        }
    )
    with pytest.raises(ValueError):
        validate_answer(draft, search_result())


def test_answer_with_exact_quote_and_abstention():
    draft = AnswerDraft.model_validate(
        {
            "claims": [
                {
                    "text": "fixture",
                    "citations": [{"source_id": 1, "quote": "Synthetic test evidence"}],
                }
            ]
        }
    )
    result = validate_answer(draft, search_result())
    assert result.answer == "fixture [1]" and result.status == "answered"
    assert validate_answer(AnswerDraft(), search_result()).status == "insufficient_evidence"


def test_missing_database_fails_before_paid_embedding(monkeypatch):
    settings = Settings(_env_file=None, database_url=None, dashscope_api_key="fixture")

    def fail(*args):
        pytest.fail("Embedding must not run before the database check")

    service = RagService(settings)
    monkeypatch.setattr(service.embeddings, "embed", fail)
    with pytest.raises(ServiceError) as caught:
        service.index(paper())
    assert caught.value.code == "database_not_configured"


@pytest.mark.api
def test_knowledge_http_validation_and_missing_database():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, database_url=None)
    try:
        with TestClient(app) as client:
            assert (
                client.post("/api/v1/knowledge/search", json={"question": " "}).status_code
                == 422
            )
            response = client.post("/api/v1/knowledge/search", json={"question": "test"})
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "database_not_configured"
    finally:
        app.dependency_overrides.clear()
