"""Synthetic evaluator unit tests; do not claim real research accuracy."""

import pytest

from scripts.evaluate_v09 import evaluate


def example(doc: str, label: str, value: float):
    return {
        "document_id": doc,
        "sample_label": label,
        "optical_band_gap_eV": value,
    }


def test_sample_identity_is_scoped_per_paper():
    gold = [example("paper-a", "S1", 3.1), example("paper-b", "S1", 3.2)]
    pred = [example("paper-b", "S1", 3.1), example("paper-a", "S1", 3.1)]
    result = evaluate(gold, pred)
    assert result["correct_sample_and_value"] == 1
    assert result["sample_value_recall"] == 0.5


def test_empty_gold_is_not_scored():
    with pytest.raises(ValueError, match="human gold"):
        evaluate([], [])


def test_duplicate_gold_label_rejected():
    with pytest.raises(ValueError, match="unique"):
        evaluate([example("paper", "S1", 3), example("paper", "s1", 4)], [])
