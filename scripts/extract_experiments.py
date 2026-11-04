"""One real structured extraction; evidence matching never means scientific verification."""

import argparse
import sys
from uuid import UUID

from app.core.config import get_settings
from app.ingestion.extractor import ExperimentExtractor
from app.services.document_service import DocumentService


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("document_id", type=UUID)
    parser.add_argument(
        "--revalidate", action="store_true", help="Recheck saved output without a new model call"
    )
    args = parser.parse_args()
    settings = get_settings()
    document = DocumentService(settings.data_dir).load(args.document_id)
    extractor = ExperimentExtractor(settings)
    result = extractor.revalidate(document) if args.revalidate else extractor.extract(document)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
