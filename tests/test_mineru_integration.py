"""Offline source-grounding tests for optional MinerU and native PDF parser."""

import json
import zipfile
from datetime import UTC, datetime
from uuid import uuid4

import pymupdf
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.ingestion.chunker import chunk_document
from app.ingestion.mineru_parser import parse_mineru_zip
from app.ingestion.pdf_parser import parse_pdf
from app.schemas.document import ParsedDocument, SourceBlock
from app.services.document_service import DocumentService


def test_mineru_zip_converts_hierarchy_to_page_coordinates(tmp_path):
    pdf = pymupdf.open()
    pdf.new_page(width=600, height=800)
    original = tmp_path / "paper.pdf"
    original.write_bytes(pdf.tobytes())
    pdf.close()
    middle = {
        "pdf_info": [
            {
                "page_idx": 0,
                "page_size": [600, 800],
                "para_blocks": [
                    {
                        "type": "title",
                        "bbox": [100, 80, 500, 110],
                        "lines": [
                            {
                                "spans": [
                                    {
                                        "type": "text",
                                        "content": "氮气退火对二氧化钛薄膜光学性能的影响",
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [100, 160, 400, 220],
                        "lines": [{"spans": [{"type": "text", "content": "3.98、3.97 eV"}]}],
                    },
                    {
                        "type": "image",
                        "bbox": [100, 240, 300, 310],
                        "lines": [{"spans": [{"type": "image", "image_path": "images/a.jpg"}]}],
                    },
                    {
                        "type": "table",
                        "bbox": [100, 320, 500, 450],
                        "blocks": [
                            {
                                "type": "table_body",
                                "table_body": (
                                "<table><tr><td>Sample</td><td>Band gap (eV)</td></tr>"
                                "<tr><td>S1</td><td>3.98</td></tr></table>"
                            ),
                            }
                        ],
                    },
                ],
            }
        ]
    }
    archive = tmp_path / "parsed.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("outputs/middle_json.json", json.dumps(middle))
    parsed = parse_mineru_zip(original, uuid4(), "paper.pdf", archive)
    assert parsed.page_count == 1
    assert parsed.title == "氮气退火对二氧化钛薄膜光学性能的影响"
    assert all(block.page_number == 1 for block in parsed.blocks)
    assert all(len(block.bbox) == 4 for block in parsed.blocks)
    assert all("data:image" not in block.text for block in parsed.blocks)
    assert any("3.98" in block.text for block in parsed.blocks)
    assert any(block.kind == "table" and "Band gap" in block.text for block in parsed.blocks)


def test_mineru_requires_structural_json(tmp_path):
    pdf = pymupdf.open()
    pdf.new_page()
    source = tmp_path / "source.pdf"
    source.write_bytes(pdf.tobytes())
    pdf.close()
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("result.md", "# title")
    with pytest.raises(ServiceError) as error:
        parse_mineru_zip(source, uuid4(), "source.pdf", archive)
    assert error.value.code == "mineru_invalid_result"


def test_native_parser_title_ignores_journal_heading(tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((50, 40), "Vol. 20, No. 1", fontsize=10)
    page.insert_text((50, 135), "Annealed titanium dioxide optical properties", fontsize=18)
    page.insert_text((50, 200), "1. Experimental preparation", fontsize=12)
    page.insert_text((50, 240), "Samples were annealed at 500 C.", fontsize=11)
    source = tmp_path / "test.pdf"
    source.write_bytes(pdf.tobytes())
    pdf.close()
    parsed = parse_pdf(source, uuid4(), "test.pdf")
    assert parsed.title == "Annealed titanium dioxide optical properties"
    assert any(block.section_title for block in parsed.blocks)


def test_semantic_chunker_filters_base64_and_keeps_source_id():
    source = "实验样品带隙是3.98 eV。" * 45
    source += "\n\n"
    source += "![](data:image/png;base64,AAABBBBB)"
    source += "\n后续结果仍然属于本章。"
    block = SourceBlock(
        block_id="p1-text-1",
        page_number=1,
        kind="text",
        bbox=(10, 10, 60, 60),
        text=source,
        raw_text=source,
        section_title="实验结果",
    )
    document = ParsedDocument(
        document_id=uuid4(),
        filename="example.pdf",
        title="Fixture",
        sha256="0" * 64,
        page_count=1,
        parsed_at=datetime.now(UTC),
        blocks=[block],
    )
    chunks = chunk_document(document, size=220, overlap=40)
    assert len(chunks) > 1
    assert all(chunk.block_id == "p1-text-1" and chunk.page_number == 1 for chunk in chunks)
    assert all("data:image" not in chunk.text for chunk in chunks)


def test_mineru_missing_configuration_is_safe(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, database_url=None, mineru_cli_path=None)
    service = DocumentService(tmp_path, settings)
    pdf = pymupdf.open()
    pdf.new_page()
    data = pdf.tobytes()
    pdf.close()
    with pytest.raises(ServiceError) as caught:
        service.ingest(data, "test.pdf", parser_engine="mineru")
    assert caught.value.code == "mineru_not_configured"
