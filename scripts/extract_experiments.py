"""One real structured extraction; evidence matching never means scientific verification."""

import argparse
import sys
from uuid import UUID

from app.core.config import LOCAL_TENANT_ID, get_settings, tenant_data_dir
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
    document = DocumentService(
        tenant_data_dir(settings, LOCAL_TENANT_ID), settings, LOCAL_TENANT_ID
    ).load(args.document_id)
    extractor = ExperimentExtractor(settings, LOCAL_TENANT_ID)
    result = extractor.revalidate(document) if args.revalidate else extractor.extract(document)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
