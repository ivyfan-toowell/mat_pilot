"""提供材料筛选、详情、晶体结构、比较和查询结果导出接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response

from app.core.config import Settings, get_settings
from app.schemas.material import (
    MATERIAL_ID_PATTERN,
    CrystalStructureResult,
    Material,
    MaterialQuery,
    MaterialSearchResult,
)
from app.science.materials_project import MaterialsProjectService
from app.services.comparison_service import ComparisonRequest, compare_materials
from app.services.material_service import QueryStore, export_csv

router = APIRouter(prefix="/api/materials", tags=["materials"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
MaterialId = Annotated[str, Path(pattern=MATERIAL_ID_PATTERN)]


@router.post("/compare")
def compare(request: ComparisonRequest, settings: SettingsDep) -> dict:
    return compare_materials(request, settings)


@router.post("/search", response_model=MaterialSearchResult)
def search_materials(query: MaterialQuery, settings: SettingsDep) -> MaterialSearchResult:
    result = MaterialsProjectService(settings).search(query)
    QueryStore(settings.data_dir).save(result)
    return result


@router.get("/queries/{query_id}", response_model=MaterialSearchResult)
def get_query(query_id: UUID, settings: SettingsDep) -> MaterialSearchResult:
    return QueryStore(settings.data_dir).load(query_id)


@router.get("/queries/{query_id}/csv")
def download_csv(query_id: UUID, settings: SettingsDep) -> Response:
    result = QueryStore(settings.data_dir).load(query_id)
    return Response(
        content="\ufeff" + export_csv(result),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="materials-{query_id}.csv"'},
    )


@router.get("/{material_id}/structure", response_model=CrystalStructureResult)
def get_structure(material_id: MaterialId, settings: SettingsDep) -> CrystalStructureResult:
    return MaterialsProjectService(settings).get_structure(material_id)


@router.get("/{material_id}", response_model=Material)
def get_material_details(material_id: MaterialId, settings: SettingsDep) -> Material:
    return MaterialsProjectService(settings).get_details(material_id)
