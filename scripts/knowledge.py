"""CLI to index a parsed document or ask an evidence-linked question."""

import argparse
import sys
from uuid import UUID

from app.core.config import get_settings
from app.schemas.retrieval import SearchRequest
from app.services.document_service import DocumentService
from app.services.rag_service import RagService


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["index", "search", "answer"])
    parser.add_argument("--document-id", type=UUID)
    parser.add_argument("--question")
    parser.add_argument("--retrieval-mode", choices=["dense", "sparse", "hybrid"], default="dense")
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    service = RagService(settings)
    if args.action == "index":
        if not args.document_id:
            parser.error("index requires --document-id")
        import json

        print(json.dumps(service.index(DocumentService(settings.data_dir).load(args.document_id))))
    else:
        if not args.question:
            parser.error("search/answer requires --question")
        request = SearchRequest(
            question=args.question,
            document_id=args.document_id,
            retrieval_mode=args.retrieval_mode,
            rerank=args.rerank,
        )
        result = getattr(service, args.action)(request)
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
