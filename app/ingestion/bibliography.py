"""Read display metadata from the PDF, without model calls or changing evidence."""

import re
import unicodedata
from pathlib import Path

import pymupdf

from app.ingestion.pdf_layout import clean_native_text
from app.schemas.document import ParsedDocument


def _compact(value: str) -> str:
    return "".join(char.casefold() for char in clean_native_text(value) if char.isalnum())


def _matching_title(text: str, target: str) -> str | None:
    lines = [clean_native_text(line) for line in text.splitlines() if line.strip()]
    for index in range(len(lines)):
        for width in range(1, 5):
            selected = lines[index : index + width]
            if _compact("".join(selected)) == target:
                joined = selected[0]
                for line in selected[1:]:
                    separator = " " if joined[-1:].isascii() and line[:1].isascii() else ""
                    joined += separator + line
                return re.sub(r"[\s*†‡\uE000-\uF8FF]+$", "", joined)
    return None


def _chinese_byline(value: str) -> list[str]:
    # Require a whole byline of short Chinese names, not prose or affiliations.
    value = clean_native_text(value)
    value = re.sub(r"[\d*†‡\uE000-\uF8FF]+", "", value)
    value = re.sub(r"(?<=[,，、])[ \t]+", "", value).strip(" ,，、")
    parts = re.split(r"[,，、;；]+", value)
    if parts and all(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", part.strip()) for part in parts):
        return list(dict.fromkeys(part.strip() for part in parts))
    return []


def read_bibliography(path: Path, document: ParsedDocument) -> tuple[str, list[str]]:
    with pymupdf.open(path) as pdf:
        metadata = pdf.metadata or {}
        native_text = pdf[0].get_text(sort=True)
    block_text = "\n".join(block.text for block in document.blocks if block.page_number == 1)
    title = re.sub(r"[\s*†‡\uE000-\uF8FF]+$", "", document.title.strip())
    filename_title = Path(document.filename).stem.strip()
    compact_name = _compact(filename_title)
    # A descriptive filename is usable only when the title occurs in the PDF.
    # Ignore separators so filename '-' can match the printed '/' in a material.
    if len(compact_name) >= 8:
        matched = _matching_title(native_text, compact_name) or _matching_title(
            block_text, compact_name
        )
        if matched:
            title = matched

    raw_authors = clean_native_text(metadata.get("author") or "")
    authors = []
    if raw_authors and not re.search(
        r"@|https?://|Microsoft|Adobe|Elsevier|Springer|Administrator|^admin$|^user$",
        raw_authors,
        re.I,
    ):
        names = re.split(r"\s*[,;，；、]\s*|\s+and\s+", raw_authors)
        if all(
            2 <= len(name) <= 100 and all(char.isalpha() or char in " .'-·’" for char in name)
            for name in names
        ):
            authors = list(dict.fromkeys(names))

    if not authors:
        # Look only immediately below the exact title, stopping at affiliations.
        # Both native and OCR text are supported; uncertain bylines stay empty.
        target = _compact(title)
        for text in (block_text, native_text):
            lines = [clean_native_text(line) for line in text.splitlines() if line.strip()]
            for index in range(len(lines)):
                for width in range(1, 5):
                    if _compact("".join(lines[index : index + width])) != target:
                        continue
                    following = lines[index + width : index + width + 3]
                    for line in following:
                        if not _compact(line):
                            continue
                        authors = _chinese_byline(unicodedata.normalize("NFKC", line))
                        break
                    if authors:
                        return title, authors
    return title, authors
