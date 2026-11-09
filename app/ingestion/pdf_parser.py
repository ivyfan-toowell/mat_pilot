"""解析文本 PDF 的页码、文本块和表格，将扫描文档标记为需要 OCR。"""

import hashlib
import logging
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pdfplumber
import pymupdf

from app.core.errors import ServiceError
from app.ingestion.pdf_layout import (
    clean_native_text,
    detect_paper_title,
    improve_sections,
    ordered_text_blocks,
)
from app.ingestion.table_parser import extract_caption_tables
from app.schemas.document import ParsedDocument, SourceBlock

logger = logging.getLogger(__name__)
MAX_PDF_BYTES = 30 * 1024 * 1024


def clean_text(text: str) -> str:
    return clean_native_text(text)


def parse_pdf(path: Path, document_id: UUID, filename: str) -> ParsedDocument:
    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise ServiceError("encrypted_pdf", "请先解密 PDF 后再上传。", 422)
            if not 1 <= len(pdf) <= 300:
                raise ServiceError("pdf_page_limit", "PDF 页数必须介于 1 和 300。", 422)
            candidates = []
            edge_counts: Counter[str] = Counter()
            warnings = []
            for index, page in enumerate(pdf):
                raw_blocks = ordered_text_blocks(page)
                text_length = 0
                for number, block in raw_blocks:
                    if block[6] != 0 or not block[4].strip():
                        continue
                    raw = block[4]
                    text_length += len(raw.strip())
                    edge = block[3] <= page.rect.height * 0.1 or block[1] >= page.rect.height * 0.92
                    signature = re.sub(r"\d+", "#", re.sub(r"\s+", " ", raw)).strip()
                    if edge:
                        edge_counts[signature] += 1
                    candidates.append((index + 1, number, block, edge, signature))
                if text_length < 40:
                    warnings.append(f"第 {index + 1} 页文本不足，可能需要 OCR；未生成猜测内容。")
            threshold = max(2, (len(pdf) + 1) // 2)
            blocks = []
            section = None
            for page_number, number, block, edge, signature in candidates:
                if edge and edge_counts[signature] >= threshold:
                    continue
                text = clean_text(block[4])
                if re.fullmatch(r"\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{2,100}", text):
                    section = text
                blocks.append(
                    SourceBlock(
                        block_id=f"p{page_number}-text-{number}",
                        page_number=page_number,
                        kind="text",
                        bbox=tuple(block[:4]),
                        text=text,
                        raw_text=block[4],
                        section_title=section,
                        role="section" if text == section else "paragraph",
                        section_path=[section] if section else [],
                    )
                )
            title = detect_paper_title(pdf, filename)
            page_count = len(pdf)
        with pdfplumber.open(path) as tables_pdf:
            for index, page in enumerate(tables_pdf.pages):
                try:
                    tables = page.find_tables()
                    if not tables:
                        tables = page.find_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "lines",
                                "min_words_vertical": 2,
                                "intersection_tolerance": 5,
                            }
                        )
                    for number, table in enumerate(tables):
                        rows = table.extract()
                        if len(rows) < 2 or max(map(len, rows), default=0) < 2:
                            continue
                        text = "\n".join(" | ".join(cell or "" for cell in row) for row in rows)
                        preceding = [
                            b
                            for b in blocks
                            if b.page_number == index + 1
                            and b.bbox[1] <= table.bbox[1]
                            and table.bbox[1] - b.bbox[1] < 100
                        ]
                        caption = next(
                            (
                                re.search(r"Table\s+(\d+)", b.text)
                                for b in reversed(preceding)
                                if re.search(r"Table\s+(\d+)", b.text)
                            ),
                            None,
                        )
                        blocks.append(
                            SourceBlock(
                                block_id=f"p{index + 1}-table-{number}",
                                page_number=index + 1,
                                kind="table",
                                bbox=tuple(table.bbox),
                                text=text,
                                raw_text=text,
                                table_number=caption.group(1) if caption else None,
                                rows=rows,
                                role="table",
                            )
                        )
                except Exception as exc:
                    logger.warning(
                        "Table parsing failed page=%d type=%s", index + 1, type(exc).__name__
                    )
                    warnings.append(f"第 {index + 1} 页表格解析失败，保留了原文和原文件。")
        blocks.extend(extract_caption_tables(path, blocks))
        if not blocks:
            warnings.append("未提取到文本或表格，请使用 OCR 解析器。")
        blocks = sorted(blocks, key=lambda b: b.page_number)
        improve_sections(blocks)
        return ParsedDocument(
            document_id=document_id,
            filename=filename,
            title=title,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            page_count=page_count,
            parsed_at=datetime.now(UTC),
            blocks=blocks,
            warnings=warnings,
            parser_engine="pymupdf",
        )
    except ServiceError:
        raise
    except Exception as exc:
        logger.warning("PDF parsing failed type=%s", type(exc).__name__)
        raise ServiceError("pdf_parse_failed", "PDF 解析失败，原文件已保留。", 422) from exc


def as_markdown(document: ParsedDocument) -> str:
    parts = [f"# {document.title}", f"Document: {document.document_id}"]
    for block in document.blocks:
        parts.extend([f"\n<!-- page={block.page_number} block={block.block_id} -->", block.text])
    return "\n\n".join(parts)
