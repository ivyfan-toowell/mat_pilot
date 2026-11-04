"""Algorithm and API safety contracts with explicitly synthetic evidence."""

from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.retrieval import SearchHit, SearchRequest
from app.services.hybrid_retrieval import (
    deduplicate,
    reciprocal_rank_fusion,
    sparse_search,
    tokenize,
)
from app.services.rag_service import RagService
from app.services.rerank_service import RerankService


def hit(text, *, similarity=None, **kwargs):
    return SearchHit(
        chunk_id=uuid4(),
        document_id=uuid4(),
        block_id="fixture-block",
        page_number=1,
        kind="text",
        text=text,
        title="Synthetic test corpus",
        similarity=similarity,
        **kwargs,
    )


def test_tokenizer_keeps_formula_sample_number_and_chinese_terms():
    tokens = tokenize("TiO₂-24 的光学带隙是 3.42 eV")
    assert {"tio2-24", "tio2", "24", "3.42", "ev", "光学"}.issubset(tokens)


def test_sparse_matches_terms_without_embedding_or_unrelated_documents():
    chunks = [hit("Synthetic TiO2 optical absorption test"), hit("Synthetic aluminum lattice")]
    result = sparse_search("TiO₂ optical", chunks, 5)
    assert len(result) == 1 and result[0].chunk_id == chunks[0].chunk_id
    assert result[0].sparse_score > 0 and result[0].similarity is None
    assert sparse_search("xyzabsent", chunks, 5) == []
    assert sparse_search("?!", chunks, 5) == []


def test_fusion_uses_ranks_and_keeps_both_score_types():
    a, b, c = [hit(text, similarity=score) for text, score in [("a", 0.99), ("b", 0.7), ("c", 0.5)]]
    sparse_b = b.model_copy(update={"similarity": None, "sparse_score": 10000})
    sparse_c = c.model_copy(update={"similarity": None, "sparse_score": 0.01})
    result = reciprocal_rank_fusion([[a, b], [sparse_b, sparse_c]])
    assert [item.text for item in result] == ["b", "a", "c"]
    assert result[0].rrf_score == pytest.approx(1 / 62 + 1 / 61)
    assert result[0].similarity == 0.7 and result[0].sparse_score == 10000
    assert a.rrf_score is None


def test_exact_duplicate_uploads_do_not_outvote_distinct_measurements():
    a = hit("Synthetic TiO2-24 3.42 eV", source_url="https://example.invalid/fixture")
    duplicate = a.model_copy(update={"chunk_id": uuid4(), "document_id": uuid4()})
    different = a.model_copy(update={"chunk_id": uuid4(), "text": "Synthetic TiO2-48 3.09 eV"})
    assert deduplicate([a, duplicate, different]) == [a, different]
    fused = reciprocal_rank_fusion([[a, duplicate, different]])
    assert len(fused) == 2 and fused[0].rrf_score == pytest.approx(1 / 61)


def test_sparse_service_never_calls_embedding_and_reports_truncation(monkeypatch):
    service = RagService(Settings(_env_file=None, dashscope_api_key=None))
    monkeypatch.setattr(service.store, "initialize", lambda: None)
    monkeypatch.setattr(service.store, "list_chunks", lambda *args: ([hit("Synthetic TiO2")], True))

    def forbidden(*args):
        pytest.fail("BM25 must not make a paid embedding request")

    monkeypatch.setattr(service.embeddings, "embed", forbidden)
    result = service.search(SearchRequest(question="TiO2", retrieval_mode="sparse"))
    assert len(result.hits) == 1 and result.embedding_model is None
    assert result.warnings and result.retrieval_mode == "sparse"


def test_rerank_preserves_source_identity_text_and_scores(monkeypatch):
    sources = [hit("Synthetic first", similarity=0.9), hit("Synthetic second", similarity=0.7)]

    def post(self, url, *, headers, json):
        assert json["input"]["documents"] == [item.text for item in sources]
        assert json["model"] == "qwen3-rerank" and json["parameters"]["top_n"] == 2
        return httpx.Response(
            200,
            json={
                "output": {
                    "results": [
                        {"index": 0, "relevance_score": 0.1},
                        {"index": 1, "relevance_score": 0.9},
                    ]
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    result = RerankService(Settings(_env_file=None, dashscope_api_key="fixture")).rank(
        "test", sources, 2
    )
    assert result[0].chunk_id == sources[1].chunk_id
    assert result[0].text == sources[1].text and result[0].similarity == 0.7
    assert result[0].rerank_score == 0.9 and sources[1].rerank_score is None


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"index": 2, "relevance_score": 0.5}],
        [{"index": True, "relevance_score": 0.5}],
        [{"index": 0, "relevance_score": "0.5"}],
        [{"index": 0, "relevance_score": 1.1}],
        [{"index": 0, "relevance_score": True}],
        [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.4}],
    ],
)
def test_rerank_invalid_provider_output_is_rejected(monkeypatch, rows):
    def post(self, url, **kwargs):
        return httpx.Response(
            200, json={"output": {"results": rows}}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(ServiceError) as error:
        RerankService(Settings(_env_file=None, dashscope_api_key="fixture")).rank(
            "test", [hit("one"), hit("two")], min(2, max(1, len(rows)))
        )
    assert error.value.code == "rerank_failed"
