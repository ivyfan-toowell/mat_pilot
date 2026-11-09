"""定义知识库检索、来源定位和带引用答案的数据结构。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    block_id: str
    page_number: int
    kind: Literal["text", "table"]
    text: str
    title: str
    source_url: str | None = None
    license: str | None = None
    section_path: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    document_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=12)
    min_similarity: float = Field(default=0.25, ge=-1, le=1)
    retrieval_mode: Literal["dense", "sparse", "hybrid"] = "dense"
    candidate_k: int = Field(default=24, ge=12, le=100)
    rerank: bool = False


class IndexResult(BaseModel):
    document_id: str
    chunks: int
    embedding_model: str
    dimensions: int


class SearchHit(Chunk):
    similarity: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class SearchResult(BaseModel):
    question: str
    hits: list[SearchHit]
    embedding_model: str | None
    retrieval_mode: Literal["dense", "sparse", "hybrid"] = "dense"
    rerank_model: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CitationQuote(BaseModel):
    source_id: int = Field(ge=1, le=12)
    quote: str = Field(min_length=1, max_length=3000, pattern=r"\S")


class AnswerClaim(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    citations: list[CitationQuote] = Field(min_length=1, max_length=12)


class AnswerDraft(BaseModel):
    claims: list[AnswerClaim] = Field(default_factory=list, max_length=20)


class AnswerResult(BaseModel):
    question: str
    status: Literal["answered", "insufficient_evidence"]
    answer: str
    claims: list[AnswerClaim] = Field(default_factory=list)
    sources: list[SearchHit] = Field(default_factory=list)
    retrieval_mode: Literal["dense", "sparse", "hybrid"] = "dense"
    rerank_model: str | None = None
    warnings: list[str] = Field(
        default_factory=lambda: [
            "引用已关联原文，但模型的语义解释仍需科研人员核查；相似度不是置信概率。"
        ]
    )
