"""Offline tests use synthetic examples, never empirical scientific claims."""

from uuid import uuid4

import pytest

from app.schemas.experimental_knowledge import EvidenceField, EvidenceRef, ExperimentalObservation
from app.services.experimental_comparison import compare_observations, compare_pair


def observed_field(doc, value):
    return EvidenceField(
        value=value,
        status="reported",
        evidence=[EvidenceRef(document_id=doc, block_id="p1-text-1", page_number=1, quote=value)],
    )


def build(**changes):
    doc = uuid4()
    base = dict(
        tenant_id="local",
        document_id=doc,
        local_sample_label=observed_field(doc, "S1"),
        formula=observed_field(doc, "TiO2"),
        phase=observed_field(doc, "anatase"),
        doping=observed_field(doc, "undoped"),
        measurement_technique=observed_field(doc, "UV-Vis DRS"),
        analysis_method=observed_field(doc, "Tauc"),
        transition_assumption=observed_field(doc, "indirect"),
        preparation_method=observed_field(doc, "annealing"),
        preparation_temperature=observed_field(doc, "500 C"),
        preparation_time=observed_field(doc, "2 h"),
        preparation_atmosphere=observed_field(doc, "air"),
        measurement_conditions=observed_field(doc, "room temperature"),
        property_value=3.1,
        property_evidence=[
            EvidenceRef(document_id=doc, block_id="p1-table-1", page_number=1, quote="S1 3.1 eV")
        ],
        verification_status="human_verified",
    )
    base.update(changes)
    return ExperimentalObservation(**base)


def test_equal_approved_records_comparable():
    assert compare_pair(build(), build()).status == "comparable"


def test_unreviewed_requires_caution():
    assert (
        compare_pair(build(), build(verification_status="evidence_matched_needs_review")).status
        == "caution"
    )


def test_missing_method_blocks_comparability():
    assert (
        compare_pair(build(), build(analysis_method=EvidenceField())).status
        == "insufficient_evidence"
    )


def test_phase_change_incompatible():
    item, other = build(), build()
    other.phase = observed_field(other.document_id, "rutile")
    assert compare_pair(item, other).status == "incompatible"


def test_same_label_different_papers_have_distinct_identity():
    a, b = build(), build()
    assert a.document_id != b.document_id and a.sample_id != b.sample_id
    assert compare_pair(a, b).status == "comparable"


def test_temperature_difference_is_caution_not_causation():
    item, other = build(), build()
    other.preparation_temperature = observed_field(other.document_id, "600 C")
    report = compare_pair(item, other)
    assert report.status == "caution"
    assert any(reason.field == "preparation_temperature" for reason in report.reasons)


def test_tenant_isolation():
    with pytest.raises(ValueError, match="cross tenant"):
        compare_pair(build(), build(tenant_id="elsewhere"))


def test_invalid_cross_document_evidence():
    doc = uuid4()
    with pytest.raises(ValueError, match="cross-document"):
        build(formula=observed_field(doc, "TiO2"))


def test_missing_reported_evidence():
    with pytest.raises(ValueError):
        EvidenceField(value="3.1 eV", status="reported")


def test_batch_limit():
    with pytest.raises(ValueError, match="maximum"):
        compare_observations([build() for _ in range(51)])
