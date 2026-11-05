"""Reject unsupported scientific values independently of LLM output quality."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ingestion.extractor import validate_candidate
from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.experiment import ExperimentCandidate


@pytest.fixture
def evidence_document():
    return ParsedDocument(
        document_id=uuid4(),
        filename="synthetic-only.pdf",
        title="Synthetic evidence test",
        sha256="0" * 64,
        page_count=5,
        parsed_at=datetime.now(UTC),
        blocks=[
            SourceBlock(
                block_id="p5-table-0",
                page_number=5,
                kind="table",
                bbox=(0, 0, 100, 100),
                text="Synthetic example. Sample | Eg (eV)\nTiO2-24 | 3.42",
                raw_text="Synthetic example. Sample | Eg (eV)\nTiO2-24 | 3.42",
                table_number="1",
            )
        ],
    )


def candidate(**overrides):
    data = {
        "material_formula": "TiO2",
        "sample_label": "TiO2-24",
        "property_name": "band_gap",
        "property_value": 3.42,
        "property_unit": "eV",
        "evidence": [{"block_id": "p5-table-0", "quote": "TiO2-24 | 3.42"}],
    }
    data.update(overrides)
    return ExperimentCandidate.model_validate(data)


def test_quote_match_keeps_page_and_review_state(evidence_document):
    result = validate_candidate(candidate(), evidence_document)
    assert result.page_number == 5 and result.table_number == "1"
    assert result.verification_status == "evidence_matched_needs_review"
    assert result.missing_fields == ["experimental_method", "experimental_conditions"]
    assert result.data_kind == "paper_experimental_estimate"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"property_value": 2.0}, "value_not_in_evidence"),
        ({"experimental_method": "invented measurement"}, "method_or_conditions_not_in_evidence"),
        ({"experimental_conditions": "heated at 900 C"}, "method_or_conditions_not_in_evidence"),
        ({"sample_label": "different-sample"}, "material_or_sample_not_in_evidence"),
        ({"material_formula": "ZnO"}, "material_or_sample_not_in_evidence"),
        (
            {"evidence": [{"block_id": "p5-table-0", "quote": "TiO2-24 | 2.00"}]},
            "quote_not_in_source",
        ),
        ({"evidence": [{"block_id": "fake", "quote": "TiO2-24 | 3.42"}]}, "unknown_evidence_block"),
    ],
)
def test_unsupported_fields_are_rejected(evidence_document, overrides, reason):
    with pytest.raises(ValueError, match=reason):
        validate_candidate(candidate(**overrides), evidence_document)


@pytest.mark.parametrize("overrides", [{"property_value": float("nan")}, {"property_unit": "nm"}])
def test_invalid_numeric_value_or_unit(overrides):
    with pytest.raises(ValidationError):
        candidate(**overrides)


def test_unquoted_context_is_removed_without_changing_supported_value(evidence_document):
    from app.ingestion.extractor import evaluate_candidates
    from app.schemas.experiment import ExtractionCandidates

    output = evaluate_candidates(
        ExtractionCandidates(experiments=[candidate(experimental_method="unquoted paraphrase")]),
        evidence_document,
        "test-only-model",
    )
    assert len(output.experiments) == 1
    assert output.experiments[0].property_value == 3.42
    assert output.experiments[0].experimental_method is None
    assert output.field_issues[0]["field"] == "experimental_method"
    assert output.rejected == []


def test_selected_method_and_conditions_are_copied_from_source(evidence_document):
    from app.ingestion.extractor import evaluate_selections
    from app.schemas.selection import SelectedExperiments

    evidence_document.blocks.append(
        SourceBlock(
            block_id="method",
            page_number=3,
            kind="text",
            bbox=(0, 0, 1, 1),
            text="Synthetic optical method\nSynthetic scanning range",
            raw_text="",
        )
    )
    selection = SelectedExperiments.model_validate(
        {
            "experiments": [
                {
                    **candidate().model_dump(
                        exclude={"evidence", "experimental_method", "experimental_conditions"}
                    ),
                    "evidence": [{"block_id": "p5-table-0", "start_line": 2, "end_line": 2}],
                    "method_evidence": {"block_id": "method", "start_line": 1, "end_line": 1},
                    "conditions_evidence": {"block_id": "method", "start_line": 2, "end_line": 2},
                }
            ]
        }
    )
    output = evaluate_selections(selection, evidence_document, "test", False)
    assert not output.rejected
    assert output.experiments[0].experimental_method == "Synthetic optical method"
    assert output.experiments[0].experimental_conditions == "Synthetic scanning range"
    selection.experiments[0].property_value = 99
    assert evaluate_selections(selection, evidence_document, "test", False).rejected


def test_empty_retry_preserves_existing_records(evidence_document, workspace_dir, monkeypatch):
    import httpx

    from app.core.config import Settings
    from app.ingestion.extractor import ExperimentExtractor

    folder = (
        workspace_dir / "tenants" / "local" / "documents" / str(evidence_document.document_id)
    )
    folder.mkdir(parents=True)
    original = '{"fixture":"previously accepted dataset"}'
    (folder / "experiments.json").write_text(original, encoding="utf-8")

    def post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"experiments":[]}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    settings = Settings(
        _env_file=None,
        data_dir=workspace_dir,
        database_url=None,
        dashscope_api_key="fixture",
    )
    result = ExperimentExtractor(settings).extract(evidence_document)
    assert result.experiments == []
    assert (folder / "experiments.json").read_text(encoding="utf-8") == original
    assert list(folder.glob("extraction-attempt-*.json"))
