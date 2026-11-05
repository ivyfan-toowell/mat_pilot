"""Live dense/BM25/RRF/Rerank pilot on one licensed paper; remote calls incur cost."""

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from time import perf_counter
from uuid import UUID

from app.core.config import PROJECT_ROOT, get_settings
from app.evaluation.retrieval import retrieval_metrics
from app.ingestion.extractor import normalized
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval import deduplicate, reciprocal_rank_fusion, sparse_search
from app.services.rerank_service import RerankService
from app.services.vector_store import VectorStore


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", type=UUID, required=True)
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "eval/retrieval_pilot.json")
    parser.add_argument("--skip-rerank", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    from app.core.config import LOCAL_TENANT_ID, tenant_data_dir

    document = DocumentService(
        tenant_data_dir(settings, LOCAL_TENANT_ID), settings, LOCAL_TENANT_ID
    ).load(args.document_id)
    if document.sha256 != dataset["sha256"]:
        raise ValueError("Dataset labels belong to a different paper SHA256")
    blocks = {block.block_id: block.text for block in document.blocks}
    for item in dataset["questions"]:
        for block_id, quote in item["evidence"].items():
            if normalized(quote) not in normalized(blocks[block_id]):
                raise ValueError(f"Ground truth quote absent: {item['id']}/{block_id}")
    store = VectorStore(settings, LOCAL_TENANT_ID)
    store.verify_embedding_config()
    chunks, truncated = store.list_chunks(args.document_id, settings.sparse_corpus_limit)
    if truncated or not chunks:
        raise ValueError("Pilot requires the complete indexed paper")
    started = perf_counter()
    vectors = EmbeddingService(settings).embed([item["question"] for item in dataset["questions"]])
    embedding_seconds = perf_counter() - started
    records = []
    for item, vector in zip(dataset["questions"], vectors, strict=True):
        dense = deduplicate(store.search(vector, args.document_id, 24, 0.25))
        sparse = sparse_search(item["question"], chunks, 24)
        fused = reciprocal_rank_fusion([dense, sparse])[:24]
        strategies = {"dense": dense, "sparse": sparse, "hybrid": fused}
        rerank_seconds = None
        if not args.skip_rerank:
            started = perf_counter()
            strategies["hybrid_rerank"] = RerankService(settings).rank(item["question"], fused, 5)
            rerank_seconds = perf_counter() - started
        rankings = {}
        for name, hits in strategies.items():
            rankings[name] = {
                "metrics_at_5": retrieval_metrics(
                    [hit.block_id for hit in hits], set(item["evidence"]), 5
                ),
                "hits": [hit.model_dump(mode="json") for hit in hits[:5]],
            }
        records.append({**item, "rankings": rankings, "rerank_seconds": rerank_seconds})
        print(
            json.dumps(
                {
                    "question": item["id"],
                    **{name: result["metrics_at_5"] for name, result in rankings.items()},
                }
            ),
            flush=True,
        )
    summary = {
        name: {
            metric: mean(row["rankings"][name]["metrics_at_5"][metric] for row in records)
            for metric in ("recall", "mrr", "ndcg")
        }
        for name in records[0]["rankings"]
    }
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": dataset["name"],
        "annotation_status": dataset["annotation_status"],
        "document_id": str(args.document_id),
        "sha256": document.sha256,
        "indexed_chunks": len(chunks),
        "questions": len(records),
        "k": 5,
        "candidate_k": 24,
        "min_similarity": 0.25,
        "rrf_k": 60,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_seconds_batched": embedding_seconds,
        "rerank_model": None if args.skip_rerank else settings.rerank_model,
        "versions": {
            "python": platform.python_version(),
            **{name: version(name) for name in ("jieba", "rank-bm25")},
        },
        "limitations": [
            "单篇论文的开发者标注试验，不代表跨论文泛化或独立盲测。",
            "相关性按证据块二值标注；同块的重复分片不重复计分；未覆盖全部可能相关段落。",
            "批量复用问题向量以控制成本，耗时不等于在线请求延迟。",
        ],
        "summary": summary,
        "records": records,
    }
    target = settings.data_dir / "acceptance" / "retrieval-pilot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(target), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
