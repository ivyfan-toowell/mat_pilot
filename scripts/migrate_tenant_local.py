"""将扁平 data/ 资产迁移到 tenants/local，并为向量表回填 tenant_id。"""

from __future__ import annotations

import shutil

from app.core.config import LOCAL_TENANT_ID, get_settings
from app.services.vector_store import VectorStore

FLAT_DIRS = ("documents", "material_queries", "literature_queries", "agent_runs")


def main() -> None:
    settings = get_settings()
    target = settings.data_dir / "tenants" / LOCAL_TENANT_ID
    target.mkdir(parents=True, exist_ok=True)
    moved = []
    for name in FLAT_DIRS:
        source = settings.data_dir / name
        destination = target / name
        if not source.exists():
            continue
        if destination.exists():
            raise SystemExit(f"目标已存在，请先处理冲突：{destination}")
        shutil.move(str(source), str(destination))
        moved.append(name)

    database = "skipped_no_database"
    if settings.database_url:
        from app.services.schema import apply_schema

        apply_schema(settings)
        store = VectorStore(settings, LOCAL_TENANT_ID)
        with store.connect() as conn:
            docs = conn.execute(
                "UPDATE mp_documents SET tenant_id=%s WHERE tenant_id IS NULL OR tenant_id=''",
                (LOCAL_TENANT_ID,),
            )
            chunks = conn.execute(
                "UPDATE mp_chunks SET tenant_id=%s WHERE tenant_id IS NULL OR tenant_id=''",
                (LOCAL_TENANT_ID,),
            )
            database = f"documents={docs.rowcount},chunks={chunks.rowcount}"
    print({"tenant": LOCAL_TENANT_ID, "moved": moved, "database": database})


if __name__ == "__main__":
    main()
