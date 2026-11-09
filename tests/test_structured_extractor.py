"""Offline fixtures for conservative evidence-linked extraction."""
from datetime import UTC, datetime
from uuid import uuid4
from app.ingestion.structured_extractor import (
    ExtractionSelection, FieldSelection, ObservationSelection, extract_from_selections,
)
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.selection import BlockSelection

def paper():
    return ParsedDocument(
        document_id=uuid4(), filename="synthetic.pdf", title="Synthetic fixture",
        sha256="0" * 64, page_count=1, parsed_at=datetime.now(UTC),
        blocks=[SourceBlock(
            block_id="p1-text-0", page_number=1, kind="text",
            bbox=(0, 0, 100, 20),
            raw_text="Sample S1 TiO2 optical band gap 3.1 eV",
            text="Sample S1 TiO2 optical band gap 3.1 eV")],
    )

def selection(value=3.1, label="S1"):
    block = BlockSelection(block_id="p1-text-0", start_line=1, end_line=1)
    return ExtractionSelection(observations=[ObservationSelection(
        fields={
            "local_sample_label": FieldSelection(
                value=label, status="reported", spans=[block]),
            "formula": FieldSelection(value="TiO2", status="reported", spans=[block]),
        },
        property_value=value, property_spans=[block],
    )])

def test_sample_level_valid_evidence():
    document = paper()
    observations, errors = extract_from_selections(document, "local", selection())
    assert not errors
    assert len(observations) == 1
    assert observations[0].local_sample_label.value == "S1"
    assert observations[0].property_value == 3.1
    assert observations[0].verification_status == "evidence_matched_needs_review"

def test_reject_missing_numeric_value():
    observations, errors = extract_from_selections(paper(), "local", selection(value=8.9))
    assert observations == [] and errors

def test_reject_wrong_sample():
    observations, errors = extract_from_selections(paper(), "local", selection(label="S2"))
    assert observations == [] and errors

def test_missing_technique_is_not_reported():
    observations, _ = extract_from_selections(paper(), "local", selection())
    assert observations[0].measurement_technique.status == "not_extracted"
