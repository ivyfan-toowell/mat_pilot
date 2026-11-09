"""V0.10 parser -> grouped chunks -> evidence/Agent citation regression.

Synthetic fixtures, no LLM, GPU, API or copyrighted PDFs.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.ingestion.chunker import chunk_document
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.experimental_knowledge import EvidenceField, EvidenceRef, ExperimentalObservation
from app.schemas.retrieval import (
    AnswerClaim,
    AnswerDraft,
    CitationQuote,
    SearchHit,
    SearchResult,
)
from app.services.evidence_audit import audit_observation
from app.services.rag_service import verify_original_citations


def _document():
    identifier = uuid4()
    blocks = [
        SourceBlock(
            block_id="p1-heading",
            page_number=1,
            kind="text",
            bbox=(10, 10, 180, 30),
            text="2.4 吸收光谱",
            raw_text="2.4 吸收光谱",
            role="section",
            section_title="2.4 吸收光谱",
            section_path=["2 结果与讨论", "2.4 吸收光谱"],
        ),
        SourceBlock(
            block_id="p1-a",
            page_number=1,
            kind="text",
            bbox=(10, 40, 180, 90),
            text="S1 TiO2 样品来自氮气退火。",
            raw_text="S1 TiO2 样品来自氮气退火。",
            section_title="2.4 吸收光谱",
            section_path=["2 结果与讨论", "2.4 吸收光谱"],
        ),
        SourceBlock(
            block_id="p1-b",
            page_number=1,
            kind="text",
            bbox=(10, 100, 180, 160),
            text="S1 TiO2 optical band gap 3.98 eV。",
            raw_text="S1 TiO2 optical band gap 3.98 eV。",
            section_title="2.4 吸收光谱",
            section_path=["2 结果与讨论", "2.4 吸收光谱"],
        ),
        SourceBlock(
            block_id="p1-table",
            page_number=1,
            kind="table",
            role="table",
            bbox=(10, 170, 180, 300),
            text="sample | gap eV\nS1 | 3.98\nS2 | 3.97",
            raw_text="sample | gap eV\nS1 | 3.98\nS2 | 3.97",
            section_title="2.4 吸收光谱",
            section_path=["2 结果与讨论", "2.4 吸收光谱"],
        ),
        SourceBlock(
            block_id="p2-a",
            page_number=2,
            kind="text",
            bbox=(10, 40, 180, 90),
            text="![](data:image/png;base64,AAABBB)\n本页其它研究结果。",
            raw_text="本页其它研究结果。",
            section_title="3 结论",
            section_path=["3 结论"],
        ),
    ]
    return ParsedDocument(
        document_id=identifier,
        filename="synthetic.pdf",
        title="TiO2 OCR fixture",
        sha256="0" * 64,
        page_count=2,
        parsed_at=datetime.now(UTC),
        blocks=blocks,
        parser_engine="mineru",
    )


def _observation(doc):
    def reference(block_id, quote, page=1):
        return EvidenceRef(
            document_id=doc.document_id,
            block_id=block_id,
            page_number=page,
            quote=quote,
        )

    identity = reference("p1-b", "S1 TiO2 optical band gap 3.98 eV。")
    return ExperimentalObservation(
        tenant_id="local",
        document_id=doc.document_id,
        local_sample_label=EvidenceField(
            value="S1",
            status="reported",
            evidence=[identity],
        ),
        formula=EvidenceField(value="TiO2", status="reported", evidence=[identity]),
        property_value=3.98,
        property_evidence=[identity],
    )


def test_section_aware_chunks_keep_all_source_ids_and_table_header():
    document = _document()
    chunks = chunk_document(document, size=180, overlap=30)
    assert chunks[0].section_path == ["2 结果与讨论", "2.4 吸收光谱"]
    assert chunks[0].source_block_ids == ["p1-a", "p1-b"]
    assert all(chunk.page_number == 1 for chunk in chunks[:2])
    assert chunks[1].kind == "table"
    assert "sample | gap eV" in chunks[1].text
    assert chunks[1].source_block_ids == ["p1-table"]
    assert all("data:image" not in chunk.text for chunk in chunks)
    assert chunks[-1].page_number == 2
    assert all(
        source_id in {block.block_id for block in document.blocks}
        for chunk in chunks
        for source_id in chunk.source_block_ids
    )


def test_evidence_audit_checks_raw_page_and_numeric_link():
    document = _document()
    record = _observation(document)
    result = audit_observation(document, record)
    assert result.valid
    assert result.checked_references == 3
    assert "OCR" in result.warnings[0]
    bad = record.model_copy(
        update={
            "property_evidence": [
                record.property_evidence[0].model_copy(update={"quote": "3.68 eV"})
            ]
        }
    )
    failed = audit_observation(document, bad)
    assert not failed.valid
    assert "property:quote_not_in_parsed_source" in failed.issues
    assert "property:numeric_value_not_in_evidence" in failed.issues
    wrong_page = record.model_copy(
        update={
            "property_evidence": [record.property_evidence[0].model_copy(update={"page_number": 2})]
        }
    )
    assert "property:page_mismatch" in audit_observation(document, wrong_page).issues


def test_agent_citations_must_exist_in_specific_original_block():
    document = _document()
    chunk = chunk_document(document, size=180, overlap=30)[0]
    hit = SearchHit(**chunk.model_dump())
    result = SearchResult(
        question="S1 带隙?",
        hits=[hit],
        embedding_model="test",
    )
    valid = AnswerDraft(
        claims=[
            AnswerClaim(
                text="S1 带隙是 3.98 eV",
                citations=[
                    CitationQuote(source_id=1, quote="optical band gap 3.98 eV"),
                ],
            ),
        ]
    )
    verify_original_citations(valid, result, {document.document_id: document})
    bad = AnswerDraft(
        claims=[
            AnswerClaim(
                text="混合两段",
                citations=[
                    CitationQuote(source_id=1, quote="来自氮气退火。\n\n[来源块 p1-b]"),
                ],
            ),
        ]
    )
    with pytest.raises(ValueError, match="citation_not_in_original_pdf_block"):
        verify_original_citations(bad, result, {document.document_id: document})
