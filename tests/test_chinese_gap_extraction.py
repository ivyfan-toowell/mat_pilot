"""Offline regression cases derived from two user-reviewed Chinese research papers.

Synthetic text only: no copyrighted PDF fixtures or live LLM calls.
"""
from datetime import UTC, datetime
from uuid import uuid4

from app.ingestion.chinese_gap_series import extract_chinese_gap_series
from app.ingestion.pdf_parser import clean_text
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.experimental_knowledge import EvidenceField


def make_document(*, author_data=True, has_unit=True, has_method=True):
    pieces = [
        "TiO2属直接带隙半导体，由实验所得透射光谱数据"
        if has_method else "文献[1]报道TiO2理论带隙数据",
        "可计算各退火温度TiO2的光学带隙Eg",
        "谱透过率，d为光程。退火温度从５００℃增加到９００℃\n"
        "所对应的样品光学带隙分别为３．９８，３．９７，３．９６，３．７３，",
        "３．３０ｅＶ，光学带隙随温度的变化趋势如图５所示。"
        if has_unit else "３．３０，光学带隙随温度的变化趋势如图５所示。",
    ]
    if not author_data:
        pieces[2] = pieces[2].replace("所对应的样品光学带隙", "参考文献中的理论带隙")
    return ParsedDocument(
        document_id=uuid4(),
        filename="synthetic_cn.pdf",
        title="synthetic",
        sha256="0" * 64,
        page_count=3,
        parsed_at=datetime.now(UTC),
        blocks=[
            SourceBlock(
                block_id=f"p3-text-{i}", page_number=3, kind="text",
                bbox=(0, i * 10, 100, i * 10 + 8), text=text, raw_text=text,
            )
            for i, text in enumerate(pieces)
        ],
    )


def test_chinese_fullwidth_text_is_normalized_for_search():
    assert "3.98eV" in clean_text("光学带隙 ３．９８ｅＶ")
    assert "500°C" in clean_text("退火温度５００℃")


def test_conservative_series_creates_reviewable_derived_conditions():
    paper = make_document()
    records, warnings = extract_chinese_gap_series(paper, "local")
    assert len(records) == 5
    assert [record.property_value for record in records] == [3.98, 3.97, 3.96, 3.73, 3.30]
    assert [record.preparation_temperature.value for record in records] == [
        "500℃", "600℃", "700℃", "800℃", "900℃"
    ]
    assert all(record.local_sample_label.status == "derived" for record in records)
    assert all(record.preparation_temperature.status == "derived" for record in records)
    assert all(record.verification_status == "evidence_matched_needs_review" for record in records)
    assert all(record.property_evidence and record.property_evidence[0].page_number == 3 for record in records)
    assert warnings and "人工" in warnings[0]
    assert all(EvidenceField.model_validate(record.formula).status == "reported" for record in records)


def test_theory_or_citation_is_not_reported_experiment():
    records, _ = extract_chinese_gap_series(make_document(has_method=False), "local")
    assert records == []


def test_missing_bandgap_unit_never_emits_results():
    records, _ = extract_chinese_gap_series(make_document(has_unit=False), "local")
    assert records == []


def test_missing_matching_experiment_phrase_never_emits_results():
    records, _ = extract_chinese_gap_series(make_document(author_data=False), "local")
    assert records == []
