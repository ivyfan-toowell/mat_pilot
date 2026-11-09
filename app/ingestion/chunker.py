"""Section-aware paragraph grouping with explicit original-block provenance.

Never combine different pages, sections or tables. The original block IDs are
persisted for retrieval and downstream evidence checks.
"""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from app.schemas.document import ParsedDocument
from app.schemas.retrieval import Chunk

_IMAGE_DATA = re.compile(r"!\[[^]]*\]\(data:image/[^)]+\)", re.I)
_BOUNDARIES = re.compile(r"(?<=[。！？；;])|(?<=[.!?])\s+(?=[A-Z])|\n{2,}")


def _pieces(text: str, size: int, overlap: int) -> list[str]:
    text = _IMAGE_DATA.sub("", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        finish = min(start + size, len(text))
        if finish < len(text):
            tail = text[start + size // 2 : finish]
            matches = list(_BOUNDARIES.finditer(tail))
            if matches:
                finish = start + size // 2 + matches[-1].end()
        piece = text[start:finish].strip()
        if piece:
            parts.append(piece)
        if finish >= len(text):
            break
        start = max(start + 1, finish - overlap)
    return parts


def chunk_document(document: ParsedDocument, size: int = 1800, overlap: int = 200) -> list[Chunk]:
    if size <= overlap or overlap < 0:
        raise ValueError("chunk size must exceed nonnegative overlap")
    result: list[Chunk] = []
    pending: list[tuple[str, str]] = []
    page: int | None = None
    section: tuple[str, ...] = ()

    def emit(parts: list[tuple[str, str]], page_number: int, path: tuple[str, ...],
             kind: str = "text") -> None:
        if not parts:
            return
        ids = [block_id for block_id, _ in parts]
        # A marker remains adjacent to each source paragraph for citation review.
        body = "\n\n".join(f"[来源块 {block_id}]\n{content}" for block_id, content in parts)
        result.append(
            Chunk(
                chunk_id=uuid5(NAMESPACE_URL, (
                    f"{document.document_id}/{page_number}/{kind}/"
                    f"{','.join(ids)}/{len(result)}"
                )),
                document_id=document.document_id,
                block_id=ids[0],
                page_number=page_number,
                kind=kind,
                text=body,
                title=document.title,
                section_path=list(path),
                source_block_ids=list(dict.fromkeys(ids)),
                source_url=document.source_url,
                license=document.license,
            )
        )

    def flush() -> None:
        nonlocal pending
        if pending and page is not None:
            emit(pending, page, section)
        pending = []

    for block in document.blocks:
        content = _IMAGE_DATA.sub("", block.text).strip()
        if not content:
            continue
        path = tuple(block.section_path or ([block.section_title] if block.section_title else []))
        if block.page_number != page or path != section or block.kind == "table":
            flush()
            page, section = block.page_number, path
        if block.kind == "table":
            # One whole table is one retrieval unit, retaining its header/rows.
            emit([(block.block_id, content)], block.page_number, path, "table")
            continue
        if block.role in {"title", "section"}:
            flush()
            # Section headings are metadata; no standalone duplicate embeddings.
            continue
        for part in _pieces(content, size, overlap):
            candidate = sum(len(item[1]) + len(item[0]) + 8 for item in pending)
            if pending and candidate + len(part) + len(block.block_id) + 8 > size:
                flush()
            pending.append((block.block_id, part))
            if len(part) >= size:
                flush()
    flush()
    return result
