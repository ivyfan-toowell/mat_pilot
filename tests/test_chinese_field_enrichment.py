"""Evidence-field completeness regressions for Chinese TiO2 annealing papers."""

from datetime import UTC, datetime
from uuid import uuid4

from app.ingestion.chinese_field_enrichment import enrich_annealing_gap_records
from app.ingestion.chinese_gap_series import extract_chinese_gap_series
from app.schemas.document import ParsedDocument, SourceBlock


def paper(include_methods=True):
    lines = [
        (1, "本文利用离子注入和氮气中退火制备氮掺杂TiO2薄膜。"),
        (3, "TiO2属直接带隙半导体，由实验所得透射光谱数据"),
        (3, "根据外推法可计算各退火温度TiO2的光学带隙。"),
        (3, "退火温度从500℃增加到900℃所对应的样品光学带隙分别为3.98，3.97，3.96，3.73，"),
        (3, "3.30eV，光学带隙随温度的变化趋势如图5所示。"),
    ]
    if not include_methods:
        lines = lines[1:]
    return ParsedDocument(
        document_id=uuid4(),
        filename="fixture.pdf",
        title="synthetic",
        sha256="0" * 64,
        parsed_at=datetime.now(UTC),
        page_count=3,
        blocks=[
            SourceBlock(
                block_id=f"p{page}-text-{i}",
                page_number=page,
                kind="text",
                bbox=(0, i * 10, 100, i * 10 + 7),
                text=value,
                raw_text=value,
            )
            for i, (page, value) in enumerate(lines)
        ],
    )


def test_enrichment_includes_real_evidence_for_methods():
    doc = paper()
    records, errors = extract_chinese_gap_series(doc, "local")
    assert len(records) == 5, errors
    for record in records:
        assert record.analysis_method.value == "外推法"
        assert record.measurement_technique.value == "透射光谱"
        assert record.transition_assumption.value == "直接带隙"
        assert record.preparation_method.value == "离子注入"
        assert record.preparation_atmosphere.value == "氮气"
        assert record.doping.value == "氮掺杂"
        for field in (
            "analysis_method",
            "measurement_technique",
            "transition_assumption",
            "preparation_method",
            "preparation_atmosphere",
            "doping",
        ):
            item = getattr(record, field)
            assert item.evidence and item.status == "reported"
            assert item.value in item.evidence[0].quote


def test_no_preparation_evidence_means_no_preparation_claims():
    doc = paper(include_methods=False)
    records, errors = extract_chinese_gap_series(doc, "local")
    assert len(records) == 5, errors
    for record in records:
        assert record.preparation_atmosphere.status == "not_extracted"
        assert record.preparation_method.status == "not_extracted"
        assert record.doping.status == "not_extracted"


def test_enrichment_noop_for_empty_records():
    assert enrich_annealing_gap_records(paper(), []) == []
