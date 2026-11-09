"""Offline evaluation of sample-linked optical gaps against human annotations.

No scores are produced without genuine human gold annotations. Example:
uv run python -m scripts.evaluate_v09 --gold gold.json --predicted predictions.json
Both inputs: {"records":[{"document_id":"...", "sample_label":"S1",
"optical_band_gap_eV":3.1}, ...]}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(gold: list[dict], predicted: list[dict]) -> dict:
    if not gold:
        raise ValueError("human gold annotations are required")

    def key(record: dict) -> tuple[str, str]:
        return str(record["document_id"]), str(record["sample_label"]).strip().casefold()

    gold_map = {key(row): row for row in gold}
    predicted_map = {key(row): row for row in predicted}
    if len(gold_map) != len(gold) or len(predicted_map) != len(predicted):
        raise ValueError("sample keys must be unique per document")
    matched = 0
    for name, expected in gold_map.items():
        actual = predicted_map.get(name)
        if actual is None:
            continue
        if (
            abs(float(actual["optical_band_gap_eV"]) - float(expected["optical_band_gap_eV"]))
            <= 0.001
        ):
            matched += 1
    return {
        "gold_records": len(gold),
        "predicted_records": len(predicted),
        "correct_sample_and_value": matched,
        "sample_value_precision": matched / len(predicted) if predicted else 0,
        "sample_value_recall": matched / len(gold),
        "note": "Limited numeric agreement only; does not evaluate causal claims, "
        "extraction evidence or scientific validity.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predicted", required=True, type=Path)
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))["records"]
    predicted = json.loads(args.predicted.read_text(encoding="utf-8"))["records"]
    print(json.dumps(evaluate(gold, predicted), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
