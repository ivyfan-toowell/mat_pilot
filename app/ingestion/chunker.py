"""按页与来源块确定性切分文献文本，保留完整表格及稳定块标识。"""

from uuid import NAMESPACE_URL, uuid5

from app.schemas.document import ParsedDocument
from app.schemas.retrieval import Chunk


def chunk_document(document: ParsedDocument, size: int = 1800, overlap: int = 200) -> list[Chunk]:
    if size <= overlap or overlap < 0:
        raise ValueError("chunk size must exceed nonnegative overlap")
    chunks = []
    for block in document.blocks:
        text = block.text.strip()
        if not text:
            continue
        # Tables must retain their headers and row relationships in one retrieval unit.
        parts = (
            [text]
            if block.kind == "table"
            else [text[start : start + size] for start in range(0, len(text), size - overlap)]
        )
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
