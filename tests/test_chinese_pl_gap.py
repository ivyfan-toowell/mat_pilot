"""Chinese PL extraction: measured 2.3 eV must not be confused with cited 2.2 eV."""

from datetime import UTC, datetime
from uuid import uuid4

from app.ingestion.chinese_pl_gap import extract_chinese_pl_gap
from app.schemas.document import ParsedDocument, SourceBlock


def sample(*, measured=True):
    text = [
        "近年来CsPbBr3的本征光学带隙约2.2eV[1-3]。",
        "大小在纳米尺度范围。测试了其PL 谱,如图1所示,样品在540",
        "nm 处呈现尖锐的荧光发射",
        "峰,表明所制备的CsPbBr\n3 具有优异的光学质",
        "量[18]。通过光子能量E=hc/λ计算得其带隙约为2.3",
        "eV。",
    ]
    if not measured:
        text[1] = "引言：综述中介绍了材料的理论带隙。"
    return ParsedDocument(
        document_id=uuid4(),
        filename="synthetic_pl.pdf",
        title="Synthetic PL fixture",
        sha256="0" * 64,
        parsed_at=datetime.now(UTC),
        page_count=1,
        blocks=[
            SourceBlock(
                block_id=f"p1-text-{i}",
                page_number=1,
                kind="text",
                bbox=(300, 100 + 15 * i, 550, 110 + 15 * i),
                text=value,
                raw_text=value,
            )
            for i, value in enumerate(text)
        ],
    )


def test_measured_pl_result_is_cited_and_marked_derived():
    records, warnings = extract_chinese_pl_gap(sample(), "local")
    assert len(records) == 1
    record = records[0]
    assert record.formula.value == "CsPbBr3"
    assert record.property_value == 2.3
    assert record.local_sample_label.status == "derived"
    assert record.measurement_technique.value == "PL"
    assert record.verification_status == "evidence_matched_needs_review"
    assert any("2.3" in ref.quote for ref in record.property_evidence)
    assert warnings and "人工" in warnings[0]


def test_background_reference_not_reported_as_measured_pl_gap():
    records, warnings = extract_chinese_pl_gap(sample(measured=False), "local")
    assert records == [] and warnings == []
