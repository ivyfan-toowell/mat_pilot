"""提供科研文本分词、BM25L 检索、证据去重与排名融合。"""

import logging
import re
import unicodedata

import jieba
from rank_bm25 import BM25L

from app.core.config import PROJECT_ROOT
from app.schemas.retrieval import Chunk, SearchHit

jieba.setLogLevel(logging.WARNING)
_TOKENIZER = jieba.Tokenizer()
# Avoid a global/user temporary dictionary cache; all generated files stay in project data.
_TOKENIZER.tmp_dir = str(PROJECT_ROOT / "data" / "runtime")


def tokenize(text: str) -> list[str]:
    (PROJECT_ROOT / "data" / "runtime").mkdir(parents=True, exist_ok=True)
    text = unicodedata.normalize("NFKC", text).casefold()
    parts = re.findall(
        r"[a-zα-ω][a-zα-ω0-9]*(?:[-.][a-z0-9]+)*|\d+(?:\.\d+)?|[\u3400-\u9fff]+", text
    )
    tokens = []
    for part in parts:
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            tokens.extend(
                token for token in _TOKENIZER.cut_for_search(part, HMM=False) if token.strip()
            )
        else:
            tokens.append(part)
            if "-" in part:
                tokens.extend(part.split("-"))
    return tokens


def evidence_key(hit: Chunk) -> tuple:
    # Exact text only: almost identical sample rows may contain different measurements.
    return (
        hit.source_url or str(hit.document_id),
        hit.page_number,
        " ".join(hit.text.split()),
    )


def deduplicate(hits: list[SearchHit]) -> list[SearchHit]:
    seen = set()
    result = []
    for hit in hits:
        key = evidence_key(hit)
        if key not in seen:
            result.append(hit)
            seen.add(key)
    return result


def sparse_search(question: str, chunks: list[Chunk], top_k: int) -> list[SearchHit]:
    chunks = deduplicate([SearchHit(**chunk.model_dump()) for chunk in chunks])
    query = tokenize(question)
    if not chunks or not query:
        return []
    corpus = [tokenize(chunk.text) for chunk in chunks]
    if not any(corpus):
        return []
    scores = BM25L(corpus).get_scores(query)
    terms = set(query)
    ranked = sorted(range(len(chunks)), key=lambda index: (-scores[index], index))
    return [
        chunks[index].model_copy(update={"sparse_score": float(scores[index])})
        for index in ranked
        if scores[index] > 0 and terms.intersection(corpus[index])
    ][:top_k]


def reciprocal_rank_fusion(rankings: list[list[SearchHit]], k: int = 60) -> list[SearchHit]:
    merged = {}
    scores = {}
    for ranking in rankings:
        for rank, hit in enumerate(deduplicate(ranking), 1):
            key = evidence_key(hit)
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
            if key not in merged:
                merged[key] = hit.model_copy(deep=True)
            else:
                for field in ("similarity", "sparse_score"):
                    if (value := getattr(hit, field)) is not None:
                        setattr(merged[key], field, value)
    return [
        merged[key].model_copy(update={"rrf_score": scores[key]})
        for key in sorted(scores, key=lambda key: -scores[key])
    ]
