"""将租户目录下的 parsed.json / experiments.json 导入 Postgres SSOT（mp_docs）。"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import LOCAL_TENANT_ID, get_settings
from app.schemas.document import ParsedDocument
from app.schemas.experiment import ExtractionResult
from app.services.document_store import DocumentStore


def migrate_tenant(root: Path, store: DocumentStore) -> dict[str, int]:
    documents = 0
    experiments = 0
    docs_dir = root / "documents"
    if not docs_dir.exists():
        return {"documents": 0, "experiments": 0}
    for folder in docs_dir.iterdir():
        if not folder.is_dir():
            continue
        parsed = folder / "parsed.json"
        if not parsed.is_file():
            continue
        document = ParsedDocument.model_validate_json(parsed.read_text(encoding="utf-8"))
        if str(document.document_id) != folder.name:
            continue
        store.upsert(document)
        documents += 1
        experiments_path = folder / "experiments.json"
        if experiments_path.is_file():
            extraction = ExtractionResult.model_validate_json(
                experiments_path.read_text(encoding="utf-8")
            )
            store.save_experiments(extraction)
            experiments += 1
    return {"documents": documents, "experiments": experiments}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default=LOCAL_TENANT_ID)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("需要配置 DATABASE_URL")
    from app.services.schema import apply_schema

    apply_schema(settings)
    store = DocumentStore(settings, args.tenant_id)
    root = settings.data_dir / "tenants" / args.tenant_id
    stats = migrate_tenant(root, store)
    print({"tenant": args.tenant_id, **stats})


if __name__ == "__main__":
    main()
