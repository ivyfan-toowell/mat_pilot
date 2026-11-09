"""Fast native-PDF layout heuristics with explicit evidence, no model required."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf

from app.schemas.document import SourceBlock

_TITLE_REJECT = re.compile(
    r"^\s*(?:第\s*\d+\s*卷|第\s*\d+\s*期|Vol\.|ISSN|DOI|文章编号|"
    r"中图分类号|收稿日期|[12]\d{3}\s*年|摘要|关键词|Abstract)",
    re.I,
)
_SECTION_RE = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2}){0,3}\s+[^\d\s].{2,90}|"
    r"(?:摘要|引言|结论|参考文献|实验部分|结果与讨论)$|"
    r"(?:Introduction|Methods|Results|Discussion|Conclusions)\b.{0,70})",
    re.I,
)


def clean_native_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.replace("\x00", "").replace("\u00ad", ""))
    # OCR/text-layer PDFs can separate Chinese characters with spaces or line breaks.
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _reasonable_title(title: str) -> bool:
    text = re.sub(r"\s+", " ", title).strip()
    return (
        8 <= len(text) <= 180
        and not _TITLE_REJECT.search(text)
        and not re.search(r"\.pdf$|Microsoft Word|WPS Office|Untitled|^\d+$", text, re.I)
    )


def detect_paper_title(pdf: pymupdf.Document, filename: str) -> str:
    """Prefer dominant first-page font text over repeated journal mastheads."""
    first = pdf[0]
    candidates: list[tuple[float, float, str]] = []
    data = first.get_text("dict")
    for block in data.get("blocks", []):
        if "lines" not in block:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s.get("text", "").strip()]
            if not spans:
                continue
            line_text = clean_native_text("".join(s["text"] for s in spans))
            top = min(float(s["bbox"][1]) for s in spans)
            if top < first.rect.height * 0.09 or top > first.rect.height * 0.57:
                continue
            if not _reasonable_title(line_text):
                continue
            score = max(float(s["size"]) for s in spans)
            # Titles typically appear in the upper half, and have large type.
            candidates.append((score, top, line_text))
    metadata = clean_native_text((pdf.metadata or {}).get("title") or "")
    if candidates:
        candidates.sort(key=lambda x: (-x[0], x[1]))
        best_size, best_y, best_text = candidates[0]
        if best_size < 13 and _reasonable_title(metadata):
            return metadata
        # Join an immediately following title line with similar font size.
        following = [
            (y, value)
            for size, y, value in candidates
            if best_y < y <= best_y + best_size * 2.3
            and abs(best_size - size) <= 1.5
            and value != best_text
        ]
        if following:
            combined = best_text + "".join(value for _, value in sorted(following))
            if _reasonable_title(combined):
                return combined
        return best_text
    if _reasonable_title(metadata):
        return metadata
    name = clean_native_text(Path(filename).stem)
    return name if _reasonable_title(name) else (metadata or name or "未识别论文标题")


def ordered_text_blocks(page: pymupdf.Page) -> list[tuple[int, tuple]]:
    """Apply simple column-aware order to native PDF text blocks.

    Columns are detected only if each side has multiple non-wide blocks.
    Otherwise retain PyMuPDF's natural sorted order. Full-width top elements
    (journal/title/abstract) remain ahead of both columns.
    """
    raw = [
        (i, block)
        for i, block in enumerate(page.get_text("blocks", sort=True))
        if block[6] == 0 and str(block[4]).strip()
    ]
    width = page.rect.width
    left = [(i, b) for i, b in raw if b[2] <= width * 0.56]
    right = [(i, b) for i, b in raw if b[0] >= width * 0.44]
    if len(left) < 3 or len(right) < 3:
        return raw
    gutter = width * 0.5
    wide = [(i, b) for i, b in raw if b[0] < width * 0.44 and b[2] > width * 0.56]
    body_start = min((b[1] for _, b in left + right), default=0)
    # If full-width blocks dominate within the body, column order is uncertain.
    if len(wide) > len(raw) // 2:
        return raw
    upper = [(i, b) for i, b in wide if b[3] <= body_start + 5]
    remaining = [(i, b) for i, b in raw if i not in {j for j, _ in upper}]
    left_column = [(i, b) for i, b in remaining if (b[0] + b[2]) / 2 < gutter]
    right_column = [(i, b) for i, b in remaining if (b[0] + b[2]) / 2 >= gutter]
    return (
        sorted(upper, key=lambda x: x[1][1])
        + sorted(left_column, key=lambda x: x[1][1])
        + sorted(right_column, key=lambda x: x[1][1])
    )


def is_section(text: str) -> bool:
    value = re.sub(r"\s+", " ", text).strip()
    return len(value) <= 110 and bool(_SECTION_RE.match(value))


def improve_sections(blocks: list[SourceBlock]) -> None:
    current: str | None = None
    for block in blocks:
        if block.kind == "text" and is_section(block.text):
            current = block.text.strip()
        if block.section_title is None:
            block.section_title = current
