"""定义文献、来源块和解析结果的数据结构，保留页码与位置坐标。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
    page_count: int
    parsed_at: datetime
    has_experiments: bool = False
