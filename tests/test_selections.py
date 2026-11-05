"""Constrained source selection prevents model copying/reformatting of quotations."""

import json

import pytest

from app.agents.claims import resolve_answer
from app.schemas.agent import ToolRecord
from app.schemas.selection import LineRange, SelectedAnswer
from app.services.evidence_service import copy_range


def test_exact_source_copy_keeps_linebreaks_and_ligatures():
    text = "Header\nTiO -24 3.42\n2\nultraviolet-visible diﬀuse reﬂectance"
    assert copy_range(text, LineRange(start_line=2, end_line=3)) == "TiO -24 3.42\n2"


@pytest.mark.parametrize("start,end", [(2, 1), (1, 5)])
def test_ranges_outside_source_are_rejected(start, end):
    with pytest.raises(ValueError):
        copy_range("one\ntwo", LineRange(start_line=start, end_line=end))


def test_tool_selection_uses_exact_numeric_source_lines():
    record = ToolRecord(
        source_id=1,
        name="fixture",
        status="ok",
        arguments={},
        content=json.dumps({"fixture_value": 12}, indent=2),
    )
    selected = SelectedAnswer.model_validate(
        {
            "claims": [
                {
                    "text": "test fixture",
                    "citations": [{"source_id": 1, "start_line": 2, "end_line": 2}],
                }
            ]
        }
    )
    result = resolve_answer(selected, [record])
    assert result.claims[0].citations[0].quote == '  "fixture_value": 12'
    selected.claims[0].citations[0].start_line = 100
    with pytest.raises(ValueError):
        resolve_answer(selected, [record])


def test_decoded_multiline_evidence_uses_the_same_global_coordinates():
    record = ToolRecord(
        source_id=1,
        name="fixture",
        status="ok",
        arguments={},
        content='{\n  "evidence": "first line\\nsecond line"\n}',
    )
    selected = SelectedAnswer.model_validate(
        {
            "claims": [
                {"text": "fixture", "citations": [{"source_id": 1, "start_line": 5, "end_line": 6}]}
            ]
        }
    )
    assert resolve_answer(selected, [record]).claims[0].citations[0].quote == (
        "first line\nsecond line"
    )
