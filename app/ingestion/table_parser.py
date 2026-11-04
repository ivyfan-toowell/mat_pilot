"""依据表题和文本行补充解析仅含横线的科研表格。"""

import re
from pathlib import Path

import pdfplumber

from app.schemas.document import SourceBlock


def extract_caption_tables(path: Path, blocks: list[SourceBlock]) -> list[SourceBlock]:
    output = []
    with pdfplumber.open(path) as pdf:
        for caption in blocks:
            match = re.match(r"^Table\s+(\d+)[.:]", caption.text)
            if caption.kind != "text" or not match:
                continue
            page = pdf.pages[caption.page_number - 1]
            lines = [
                edge
                for edge in page.edges
                if abs(edge["bottom"] - edge["top"]) < 2
                and edge["width"] > page.width * 0.4
                and 0 < edge["top"] - caption.bbox[3] < 230
            ]
            if len(lines) < 2:
                continue
            first = min(lines, key=lambda edge: edge["top"])
            aligned = [
                edge
                for edge in lines
                if abs(edge["x0"] - first["x0"]) < 8 and abs(edge["x1"] - first["x1"]) < 8
            ]
            if len(aligned) < 2:
                continue
            bbox = (
                max(0, first["x0"] - 1),
                first["top"] - 1,
                min(page.width, first["x1"] + 1),
                max(edge["bottom"] for edge in aligned) + 1,
            )
            cropped = page.crop(bbox)
            tables = cropped.extract_tables(
                {
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "min_words_vertical": 2,
                }
            )
            for index, rows in enumerate(tables):
                rows = [row for row in rows if any(cell and cell.strip() for cell in row)]
                if len(rows) < 3 or max(map(len, rows), default=0) < 2:
                    continue
                raw = cropped.extract_text(x_tolerance=1) or ""
                output.append(
                    SourceBlock(
                        block_id=f"p{caption.page_number}-caption-table-{index}",
                        page_number=caption.page_number,
                        kind="table",
                        bbox=bbox,
                        text=caption.text + "\n" + raw,
                        raw_text=raw,
                        table_number=match.group(1),
                        rows=rows,
                    )
                )
    return output
