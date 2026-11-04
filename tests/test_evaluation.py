import math

import pytest

from app.evaluation.retrieval import retrieval_metrics


def test_metrics_measure_rank_recall_and_discount_without_duplicate_credit():
    scores = retrieval_metrics(["miss", "a", "a", "b"], {"a", "b"}, 4)
    assert scores["recall"] == 1
    assert scores["mrr"] == 0.5
    assert scores["ndcg"] == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    )
    assert retrieval_metrics(["miss"], {"a"}, 5) == {"recall": 0, "mrr": 0, "ndcg": 0}
    assert retrieval_metrics(["a", "b"], {"a", "b"}, 1) == {"recall": 0.5, "mrr": 1, "ndcg": 1}


def test_metrics_require_real_labels():
    with pytest.raises(ValueError):
        retrieval_metrics(["a"], set(), 5)
