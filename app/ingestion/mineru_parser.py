"""Optional MinerU 4 parser; run its CLI in a separate environment.

Consumes the 'middle_json' artifact from MinerU's ZIP export, not raw Markdown.
Fail closed when page position or recognizable text cannot be recovered.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
import unicodedata
import zipfile
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID

import pymupdf

from app.core.errors import ServiceError
from app.schemas.document import ParsedDocument, SourceBlock

logger = logging.getLogger(__name__)
MAX_EXTRACTED_BLOCKS = 10000
MAX_TEXT_BLOCK = 30000


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"tr", "p", "br"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")


def _plain(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_plain(part) for part in value)
    if isinstance(value, dict):
        return _plain(value.get("text") or value.get("content") or value.get("value"))
    text = str(value)
    if re.search(r"<(?:table|tr|td|p|br|html)\b", text, re.I):
        converter = _HTMLText()
        converter.feed(text)
        text = "".join(converter.parts)
    text = unescape(unicodedata.normalize("NFKC", text))
    # Never put inline Base64 image bytes into source blocks or embeddings.
    text = re.sub(r"!\[[^]]*\]\(data:image/[^)]+\)", "", text, flags=re.I)
    return re.sub(r"[ \t]+", " ", text).strip()


def _block_text(block: dict) -> str:
    for key in (
        "text",
        "paragraph_content",
        "title_content",
        "table_body",
        "table_caption",
        "image_caption",
        "math_content",
        "content",
    ):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return _plain(value)
        if key in {"table_caption", "image_caption"} and isinstance(value, list):
            return _plain(value)
        if key == "content" and isinstance(value, dict):
            nested = _block_text(value)
            if nested:
                return nested
    if "lines" in block:
        lines = []
        for line in block["lines"]:
            spans = line.get("spans", []) if isinstance(line, dict) else []
            lines.append(
                "".join(_plain(span.get("content", "")) for span in spans if isinstance(span, dict))
            )
        return "\n".join(line for line in lines if line).strip()
    if "blocks" in block:
        return "\n".join(
            part
            for child in block["blocks"]
            if isinstance(child, dict)
            if (part := _block_text(child))
        )
    return ""


def _page_items(payload: object) -> list[tuple[int, tuple[float, float] | None, list[dict]]]:
    """Support the middle-json page model and structured-content page groups."""
    if isinstance(payload, dict) and isinstance(payload.get("pdf_info"), list):
        pages = []
        for page in payload["pdf_info"]:
            if not isinstance(page, dict):
                continue
            items = page.get("para_blocks")
            if not isinstance(items, list):
                continue
            page_size = page.get("page_size")
            dimensions = (
                (float(page_size[0]), float(page_size[1]))
                if isinstance(page_size, list) and len(page_size) >= 2
                else None
            )
            pages.append((int(page.get("page_idx", len(pages))), dimensions, items))
        return pages
    if isinstance(payload, list) and payload and all(isinstance(p, dict) for p in payload):
        if all("page_idx" in item for item in payload):
            grouped: dict[int, list[dict]] = {}
            for item in payload:
                grouped.setdefault(int(item["page_idx"]), []).append(item)
            return [(index, None, items) for index, items in sorted(grouped.items())]
        if all(isinstance(p.get("blocks"), list) for p in payload):
            return [
                (int(page.get("page_idx", i)), None, page["blocks"])
                for i, page in enumerate(payload)
            ]
    if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
        return _page_items(payload["pages"])
    return []


def _bounds(block: dict, page_size: tuple[float, float]) -> tuple[float, float, float, float]:
    raw = block.get("bbox")
    if not isinstance(raw, (tuple, list)) or len(raw) != 4:
        raise ValueError("MinerU block has no bbox")
    values = tuple(float(v) for v in raw)
    if not (0 <= values[0] <= values[2] and 0 <= values[1] <= values[3]):
        raise ValueError("MinerU bbox is invalid")
    # In middle_json, the coordinate system is page-based; normalize only
    # boxes that exceed the original page. Never invent positions for absent bbox.
    width, height = page_size
    if values[2] > width * 1.15 or values[3] > height * 1.15:
        return (
            values[0] * width / 1000,
            values[1] * height / 1000,
            values[2] * width / 1000,
            values[3] * height / 1000,
        )
    return values


def _is_boilerplate(text: str, kind: str) -> bool:
    return kind in {"header", "footer", "page_number", "page_footnote", "aside_text"} or (
        len(text) < 100 and bool(re.search(r"^(?:第\s*\d+\s*卷|Vol\.\s*\d+)", text, re.I))
    )


def parse_mineru_zip(path: Path, document_id: UUID, filename: str, archive: Path) -> ParsedDocument:
    with pymupdf.open(path) as pdf:
        if pdf.needs_pass:
            raise ServiceError("encrypted_pdf", "请先解密 PDF 后再上传。", 422)
        if not 1 <= len(pdf) <= 300:
            raise ServiceError("pdf_page_limit", "PDF 页数必须介于 1 和 300。", 422)
        page_sizes = [(page.rect.width, page.rect.height) for page in pdf]
    try:
        with zipfile.ZipFile(archive) as zf:
            matches = [
                name
                for name in zf.namelist()
                if name.split("/")[-1] in {"middle_json.json", "structured_content.json"}
                or name.endswith("_middle.json")
            ]
            if not matches:
                raise ValueError("MinerU ZIP lacks structured JSON")
            preferred = sorted(matches, key=lambda item: "middle" not in item)
            info = zf.getinfo(preferred[0])
            if info.file_size > 50 * 1024 * 1024:
                raise ValueError("MinerU JSON exceeds safety limit")
            payload = json.loads(zf.read(info))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise ServiceError(
            "mineru_invalid_result", "MinerU 没有返回可用的结构化页码数据。", 422
        ) from exc
    pages = _page_items(payload)
    if not pages:
        raise ServiceError("mineru_invalid_result", "MinerU 结果缺少文档页及内容块。", 422)
    blocks: list[SourceBlock] = []
    warnings: list[str] = []
    title = ""
    section: str | None = None
    for page_idx, _, items in pages:
        if not 0 <= page_idx < len(page_sizes):
            raise ServiceError("mineru_invalid_result", "MinerU 返回了无效页码。", 422)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "text")
            text = _block_text(item)
            if not text or _is_boilerplate(text, kind):
                continue
            if len(text) > MAX_TEXT_BLOCK:
                warnings.append(f"第 {page_idx + 1} 页出现过长文本块，已跳过。")
                continue
            if kind in {"image", "image_body", "chart", "figure"}:
                # Only store real caption text, never image bytes or fake OCR descriptions.
                captions = _plain(item.get("image_caption") or item.get("chart_caption"))
                if not captions:
                    continue
                text = captions
            try:
                bbox = _bounds(item, page_sizes[page_idx])
            except (TypeError, ValueError):
                warnings.append(f"第 {page_idx + 1} 页某内容块缺少可靠坐标，已跳过。")
                continue
            if kind in {"title", "doc_title"}:
                if page_idx == 0 and not title and len(text) >= 8:
                    title = text.lstrip("# ").strip()
                elif page_idx > 0 or title:
                    section = text.lstrip("# ").strip()
            if kind == "table":
                block_kind = "table"
            else:
                block_kind = "text"
            blocks.append(
                SourceBlock(
                    block_id=f"p{page_idx + 1}-mineru-{index}",
                    page_number=page_idx + 1,
                    kind=block_kind,
                    bbox=bbox,
                    text=text,
                    raw_text=text,
                    section_title=section,
                )
            )
            if len(blocks) > MAX_EXTRACTED_BLOCKS:
                raise ServiceError("mineru_result_limit", "解析结果块数量超出限制。", 422)
    if not blocks:
        raise ServiceError("mineru_no_text", "MinerU 没有得到可定位的正文块。", 422)
    if not title:
        title = next((b.text for b in blocks if b.page_number == 1 and len(b.text) >= 10), "")
    warnings.append("MinerU OCR 文字可能与 PDF 字形有差异；引用原文仍需人工核对。")
    return ParsedDocument(
        document_id=document_id,
        filename=filename,
        title=title or Path(filename).stem,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        page_count=len(page_sizes),
        parsed_at=datetime.now(UTC),
        blocks=blocks,
        warnings=warnings,
    )


def parse_mineru(
    path: Path, document_id: UUID, filename: str, cli: Path, timeout: int
) -> ParsedDocument:
    if not cli.is_file():
        raise ServiceError(
            "mineru_not_configured",
            "未找到 MinerU 启动程序，请设置 MINERU_CLI_PATH 为独立环境的 mineru-kit.exe。",
            503,
        )
    with tempfile.TemporaryDirectory(prefix="matpilot-mineru-") as temporary:
        output = Path(temporary) / "result.zip"
        try:
            completed = subprocess.run(
                [
                    str(cli.resolve()),
                    "parse",
                    str(path.resolve()),
                    "-o",
                    str(output),
                    "--format",
                    "zip",
                    "--tier",
                    "standard",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ServiceError(
                "mineru_timeout", "MinerU 解析超时，请检查独立环境与 GPU。", 504
            ) from exc
        except OSError as exc:
            raise ServiceError("mineru_failed", "无法启动独立 MinerU 进程。", 503) from exc
        if completed.returncode or not output.is_file():
            # Never surface arbitrary OCR logs or local paths to API clients.
            logger.warning("MinerU failed exit_code=%s", completed.returncode)
            raise ServiceError(
                "mineru_failed", "MinerU 解析未成功；请检查独立解析环境的日志。", 502
            )
        return parse_mineru_zip(path, document_id, filename, output)
