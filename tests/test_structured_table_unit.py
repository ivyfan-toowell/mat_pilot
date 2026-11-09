"""Table-column unit linkage regressions with synthetic evidence only."""
from datetime import UTC, datetime
from uuid import uuid4

from app.ingestion.structured_extractor import (
    ExtractionSelection, FieldSelection, ObservationSelection, extract_from_selections,
)
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.selection import BlockSelection


def table_paper(header="Sample | Optical band gap (eV)", rows="S1 | 3.1\nS2 | 3.4"):
    text = header + "\n" + rows
    return ParsedDocument(
        document_id=uuid4(), filename="fixture.pdf", title="Synthetic",
        sha256="0" * 64, page_count=1, parsed_at=datetime.now(UTC),
        blocks=[SourceBlock(
            block_id="p1-table-0", page_number=1, kind="table",
            bbox=(0, 0, 100, 100), raw_text=text, text=text,
        )],
    )


def choose(document, sample="S1", value=3.1, selected_lines=(2, 2)):
    span = BlockSelection(
        block_id="p1-table-0", start_line=selected_lines[0], end_line=selected_lines[1]
    )
    return ExtractionSelection(observations=[ObservationSelection(
        fields={
            "local_sample_label": FieldSelection(
                value=sample, status="reported", spans=[span]
            ),
            "formula": FieldSelection(
                value="TiO2", status="reported", spans=[
                    BlockSelection(block_id="p1-table-0", start_line=1, end_line=1)
                ]
            ),
        },
        property_value=value, property_spans=[span],
    )])


def run(document, sample="S1", value=3.1, selected_lines=(2, 2)):
    # The synthetic chemical identity is explicitly cited in the table header.
    document.blocks[0].text = document.blocks[0].text.replace(
        "Sample |", "Sample TiO2 |", 1
    )
    return extract_from_selections(
        document, "local", choose(document, sample, value, selected_lines)
    )


def test_unit_from_header_same_table_and_correct_column():
    doc = table_paper()
    records, errors = run(doc)
    assert not errors
    assert len(records) == 1
    assert any("eV" in ref.quote for ref in records[0].property_evidence)


def test_header_without_unit_rejected():
    doc = table_paper("Sample | Optical band gap")
    records, errors = run(doc)
    assert not records
    assert "unit absent" in errors[0]


def test_other_column_not_accepted_as_gap():
    doc = table_paper("Sample | Optical band gap | mobility (eV)", "S1 | 3.1 | 8.4")
    records, errors = run(doc)
    assert not records
    assert "unit absent" in errors[0]


def test_wrong_sample_row_rejected():
    doc = table_paper()
    records, errors = run(doc, sample="S2", value=3.1)
    assert not records
    assert errors


def test_other_sample_value_same_document_rejected():
    doc = table_paper()
    records, errors = run(doc, sample="S1", value=3.4)
    assert not records
    assert errors
