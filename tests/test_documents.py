"""Synthetic PDFs test parsing mechanics; live sample acceptance is separate."""

import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import app
from app.services.document_service import DocumentService


def synthetic_pdf(*, blank=False, encrypted=False):
    pdf = pymupdf.open()
    pdf.set_metadata({"title": "Synthetic parser unit test"})
    for index in range(3):
        page = pdf.new_page()
        if not blank:
            page.insert_text((50, 15), f"Repeated test header {index + 1}")
            page.insert_text((50, 120), f"1. Test section {index + 1}")
            page.insert_text((50, 150), "Synthetic evidence only: material A has a test value.")
    if encrypted:
        data = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="test-password")
    else:
        data = pdf.tobytes()
    pdf.close()
    return data


def test_pages_sources_cleaning_and_persistence(workspace_dir):
    service = DocumentService(workspace_dir)
    source = synthetic_pdf()
    parsed = service.ingest(source, "../../paper.pdf", "https://example.org/paper", "test fixture")
    assert parsed.page_count == 3 and parsed.filename == "paper.pdf"
    assert parsed.title == "Synthetic parser unit test"
    assert not any("Repeated test header" in block.text for block in parsed.blocks)
    assert {block.page_number for block in parsed.blocks} == {1, 2, 3}
    assert len({block.block_id for block in parsed.blocks}) == len(parsed.blocks)
    assert DocumentService(workspace_dir).load(parsed.document_id) == parsed
    folder = workspace_dir / "documents" / str(parsed.document_id)
    assert (folder / "original.pdf").read_bytes() == source
    assert "page=2" in (folder / "document.md").read_text(encoding="utf-8")


def test_invalid_input_creates_no_document(workspace_dir):
    with pytest.raises(ServiceError) as caught:
        DocumentService(workspace_dir).ingest(b"not a pdf", "fake.pdf")
    assert caught.value.code == "invalid_pdf"
    assert not (workspace_dir / "documents").exists()


def test_size_is_checked_before_parsing(workspace_dir, monkeypatch):
    monkeypatch.setattr("app.services.document_service.MAX_PDF_BYTES", 16)
    with pytest.raises(ServiceError) as caught:
        DocumentService(workspace_dir).ingest(synthetic_pdf(), "paper.pdf")
    assert caught.value.status_code == 413


def test_encrypted_file_retained_with_failure(workspace_dir):
    source = synthetic_pdf(encrypted=True)
    with pytest.raises(ServiceError) as caught:
        DocumentService(workspace_dir).ingest(source, "locked.pdf")
    assert caught.value.code == "encrypted_pdf"
    folder = next((workspace_dir / "documents").iterdir())
    assert (folder / "original.pdf").read_bytes() == source
    assert json.loads((folder / "failure.json").read_text())["status"] == "failed"


def test_empty_pages_flag_ocr_without_inventing_text(workspace_dir):
    result = DocumentService(workspace_dir).ingest(synthetic_pdf(blank=True), "scan.pdf")
    assert result.blocks == []
    assert len(result.warnings) >= 3


@pytest.mark.api
def test_upload_and_reload(workspace_dir):
    settings = Settings(_env_file=None, data_dir=workspace_dir, database_url=None)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/documents",
                    files={"file": ("paper.pdf", synthetic_pdf(), "application/pdf")}
            )
            assert response.status_code == 200
            document_id = response.json()["document_id"]
            assert client.get(f"/api/v1/documents/{document_id}").json() == response.json()
            assert (
                client.post(
                    "/api/v1/documents", files={"file": ("fake.pdf", b"invalid")}
                ).status_code
                == 422
            )
    finally:
        app.dependency_overrides.clear()
