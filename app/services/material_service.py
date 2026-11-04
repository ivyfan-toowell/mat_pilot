"""保存和读取材料查询快照，并提供 CSV 导出。"""

import logging
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from app.core.errors import ServiceError
from app.schemas.material import MaterialSearchResult

logger = logging.getLogger(__name__)


class QueryStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "material_queries"

    def save(self, result: MaterialSearchResult) -> None:
        temporary: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / f"{result.query_id}.json"
            temporary = self.directory / f".{uuid4()}.tmp"
            temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(target)
        except OSError as exc:
            logger.warning("Saving query failed type=%s", type(exc).__name__)
            raise ServiceError(
                "storage_unavailable", "查询结果保存失败，请检查数据目录权限。", 503
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self, query_id: UUID) -> MaterialSearchResult:
        path = self.directory / f"{query_id}.json"
        try:
            return MaterialSearchResult.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ServiceError("query_not_found", "未找到该材料查询。", 404) from exc


def export_csv(result: MaterialSearchResult) -> str:
    columns = [
        "material_id",
        "formula",
        "band_gap_eV",
        "formation_energy_eV_per_atom",
        "energy_above_hull_eV_per_atom",
        "is_gap_direct",
        "is_stable",
        "crystal_system",
        "space_group",
        "source_database",
        "data_kind",
        "source_url",
        "data_version",
        "retrieved_at",
    ]
    rows = []
    for material in result.materials:
        row = material.model_dump(mode="json", exclude={"calculation_provenance"})
        row["band_gap_eV"] = row.pop("band_gap")
        row["formation_energy_eV_per_atom"] = row.pop("formation_energy_per_atom")
        row["energy_above_hull_eV_per_atom"] = row.pop("energy_above_hull")
        rows.append(row)
    return pd.DataFrame(rows, columns=columns).to_csv(index=False)
