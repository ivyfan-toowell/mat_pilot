"""计算文献检索的召回率、倒数排名和排序质量，避免重复证据重复计分。"""

import math


def retrieval_metrics(ranked_blocks: list[str], relevant: set[str], k: int) -> dict[str, float]:
    if k < 1 or not relevant:
        raise ValueError("positive k and nonempty relevance labels required")
    seen = set()
    dcg, first = 0.0, 0.0
    found = set()
    for rank, block in enumerate(ranked_blocks[:k], 1):
        if block in relevant and block not in seen:
            found.add(block)
            dcg += 1 / math.log2(rank + 1)
            if not first:
                first = 1 / rank
        seen.add(block)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return {"recall": len(found) / len(relevant), "mrr": first, "ndcg": dcg / ideal}
