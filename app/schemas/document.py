"""定义文献、来源块和解析结果的数据结构，保留页码与位置坐标。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("authors")
    @classmethod
    def clean_authors(cls, values: list[str]) -> list[str]:
        authors = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 200 for value in authors):
            raise ValueError("作者姓名不能超过 200 个字符")
        return authors


class SourceBlock(BaseModel):
    block_id: str
    page_number: int = Field(ge=1)
    kind: Literal["text", "table"]
    bbox: tuple[float, float, float, float]
    text: str
    raw_text: str
    section_title: str | None = None
    table_number: str | None = None
    rows: list[list[str | None]] | None = None
    # Optional semantic metadata; old stored ParsedDocument JSON remains compatible.
    role: Literal["title", "section", "paragraph", "table", "figure_caption", "formula"] = (
        "paragraph"
    )
    section_path: list[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    document_id: UUID
    filename: str
    title: str
    authors: list[str] = Field(default_factory=list)
    metadata_edited: bool = False
    deleted_at: datetime | None = None
    sha256: str
    page_count: int
    parsed_at: datetime
    blocks: list[SourceBlock]
    source_url: str | None = None
    license: str | None = None
    warnings: list[str] = Field(default_factory=list)
    parser_engine: Literal["pymupdf", "mineru"] = "pymupdf"
    parent_document_id: UUID | None = None


class DocumentSummary(BaseModel):
    document_id: UUID
    filename: str
    title: str
    authors: list[str] = Field(default_factory=list)
    parser_engine: Literal["pymupdf", "mineru"] = "pymupdf"
    page_count: int
    parsed_at: datetime
    has_experiments: bool = False
    deleted_at: datetime | None = None


class DocumentCatalogPage(BaseModel):
    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int


class DocumentStatus(BaseModel):
    document_id: UUID
    deleted_at: datetime | None
