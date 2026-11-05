"""Parse a local PDF, retaining an adjacent .source.json attribution if present."""

import argparse
import json
import sys
from pathlib import Path

from app.core.config import LOCAL_TENANT_ID, get_settings, tenant_data_dir
from app.services.document_service import DocumentService


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    metadata_path = args.path.with_suffix(".source.json")
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    )
    settings = get_settings()
    document = DocumentService(
        tenant_data_dir(settings, LOCAL_TENANT_ID), settings, LOCAL_TENANT_ID
    ).ingest(
        args.path.read_bytes(), args.path.name, metadata.get("source_url"), metadata.get("license")
    )
    print(
        json.dumps(
            {
                "document_id": str(document.document_id),
                "title": document.title,
                "pages": document.page_count,
                "blocks": len(document.blocks),
                "tables": [
                    {
                        "block_id": block.block_id,
                        "page": block.page_number,
                        "table_number": block.table_number,
                        "rows": len(block.rows or []),
                    }
                    for block in document.blocks
                    if block.kind == "table"
                ],
                "warnings": document.warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
