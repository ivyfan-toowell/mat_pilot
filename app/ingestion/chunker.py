"""Section-aware paragraph chunking with stable source-block evidence."""
from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from app.schemas.document import ParsedDocument
from app.schemas.retrieval import Chunk

_IMAGE_DATA = re.compile(r"!\\[[^]]*\\]\\(data:image/[^)]+\\)", re.I)
_BOUNDARIES = re.compile(r"(?<=[。！？!?；;])\\s+|(?<=[.!?])\\s+(?=[A-Z])|\\n{2,}")


def _pieces(text: str, size: int, overlap: int) -> list[str]:
    """Split on paragraph/sentence boundaries, never on a formula if avoidable."""
    text = _IMAGE_DATA.sub("", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    start = 0
    stride = size - overlap
    while start < len(text):
        finish = min(start + size, len(text))
        if finish < len(text):
            # Prefer the final semantic boundary in the last 50% of the window.
            tail = text[start + size // 2: finish]
            matches = list(_BOUNDARIES.finditer(tail))
            if matches:
                finish = start + size // 2 + matches[-1].end()
        piece = text[start:finish].strip()
        if piece:
            parts.append(piece)
        if finish >= len(text):
            break
        next_start = max(start + 1, finish - overlap)
        # Keep starts at natural word/paragraph positions where possible.
        if next_start - start < stride // 2:
            next_start = start + stride
        start = next_start
    return parts


def chunk_document(document: ParsedDocument, size: int = 1800, overlap: int = 200) -> list[Chunk]:
    if size <= overlap or overlap < 0:
        raise ValueError("chunk size must exceed nonnegative overlap")
    chunks: list[Chunk] = []
    for block in document.blocks:
        text = block.text.strip()
        if not text:
            continue
        # Tables stay intact so column headers and sample rows remain associated.
        parts = [text] if block.kind == "table" else _pieces(text, size, overlap)
        for index, part in enumerate(parts):
            chunks.append(
                Chunk(
                    chunk_id=uuid5(
                        NAMESPACE_URL, f"{document.document_id}/{block.block_id}/{index}"
                    ),
                    document_id=document.document_id,
                    block_id=block.block_id,
                    page_number=block.page_number,
                    kind=block.kind,
                    text=part,
                    title=document.title,
                    source_url=document.source_url,
                    license=document.license,
                )
            )
    return chunks
