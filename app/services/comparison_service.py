"""比较已保存查询中的候选材料，保留计算属性的单位、来源及局限。"""

from pathlib import Path

from app.core.config import LOCAL_TENANT_ID, Settings, tenant_data_dir
from app.core.errors import ServiceError
from app.schemas.material import ComparisonRequest, MaterialComparisonResult
from app.services.material_service import QueryStore

# Re-export for callers that historically imported schemas from this module.
__all__ = ["ComparisonRequest", "MaterialComparisonResult", "compare_materials"]


def compare_materials(
    request: ComparisonRequest,
    settings: Settings,
    tenant_id: str = LOCAL_TENANT_ID,
    data_dir: Path | None = None,
) -> MaterialComparisonResult:
    root = data_dir if data_dir is not None else tenant_data_dir(settings, tenant_id)
    result = QueryStore(root).load(request.query_id)
    candidates = {material.material_id: material for material in result.materials}
    if any(material_id not in candidates for material_id in request.material_ids):
        raise ServiceError("material_outside_query", "比较对象必须来自指定查询快照。", 422)
    selected = request.material_ids or list(candidates)
    rows = [
        {
            "material_id": material_id,
            "formula": candidates[material_id].formula,
            "band_gap_eV": candidates[material_id].band_gap,
            "energy_above_hull_eV_per_atom": candidates[material_id].energy_above_hull,
            "formation_energy_eV_per_atom": candidates[material_id].formation_energy_per_atom,
            "crystal_system": candidates[material_id].crystal_system,
            "space_group": candidates[material_id].space_group,
            "source_url": candidates[material_id].source_url,
        }
        for material_id in selected
    ]
    return MaterialComparisonResult(
        query_id=str(result.query_id),
        data_kind="computed",
        materials=rows,
        warnings=[
            *result.warnings,
            "比较限定于当前候选批次；空值保留，不依据带隙或凸包能量直接判定器件性能。",
        ],
    )
