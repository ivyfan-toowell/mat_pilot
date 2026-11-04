"""比较已保存查询中的候选材料，保留计算属性的单位、来源及局限。"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import ServiceError
from app.services.material_service import QueryStore


class ComparisonRequest(BaseModel):
    query_id: UUID
    material_ids: list[str] = Field(default_factory=list, max_length=10)


def compare_materials(request: ComparisonRequest, settings: Settings) -> dict:
    result = QueryStore(settings.data_dir).load(request.query_id)
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
    return {
        "query_id": str(result.query_id),
        "data_kind": "computed",
        "materials": rows,
        "warnings": [
            *result.warnings,
            "比较限定于当前候选批次；空值保留，不依据带隙或凸包能量直接判定器件性能。",
        ],
    }
