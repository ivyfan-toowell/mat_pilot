"""定义在线论文检索条件与元数据结果，明确其与全文证据的边界。"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class LiteratureQuery(BaseModel):
    model_config = {"extra": "forbid"}
    query: str = Field(min_length=1, max_length=300, pattern=r"\S")
    year_from: int | None = Field(default=None, ge=1600, le=2100)
    year_to: int | None = Field(default=None, ge=1600, le=2100)
    open_access_only: bool = False
    sort: Literal["relevance", "newest", "citations"] = "relevance"
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query", mode="before")
    @classmethod
    def trim_query(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_years(self):
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must not exceed year_to")
        return self


class AcademicPaper(BaseModel):
    openalex_id: str = Field(pattern=r"^https://openalex\.org/W\d+$")
    title: str | None = None
    doi: str | None = None
    doi_url: str | None = None
    authors: list[str] = Field(default_factory=list, max_length=30)
    authors_truncated: bool = False
    publication_year: int | None = Field(default=None, ge=1, le=9999)
    publication_date: date | None = None
    venue: str | None = None
    work_type: str | None = None
    cited_by_count: int | None = Field(default=None, ge=0)
    is_retracted: bool | None = None
    is_oa: bool | None = None
    oa_status: str | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    license: str | None = None
    version: str | None = None
    data_kind: Literal["bibliographic_metadata"] = "bibliographic_metadata"


class LiteratureResult(BaseModel):
    query_id: UUID
    query: LiteratureQuery
    retrieved_at: datetime
    source_database: Literal["OpenAlex"] = "OpenAlex"
    api_url: str
    matched_count: int = Field(ge=0)
    papers: list[AcademicPaper] = Field(default_factory=list, max_length=20)
    possibly_truncated: bool
    attempts: int = Field(ge=1, le=3)
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    provider_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    metadata_only: Literal[True] = True
    warnings: list[str] = Field(
        default_factory=lambda: [
            "当前结果仅为论文元数据，未下载、解析或核验全文，不能据此确认实验数值或科研结论。",
            "开放获取标记和链接不等于再分发许可；下载或使用全文前请核对原文许可。",
        ]
    )
