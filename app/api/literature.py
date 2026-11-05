"""提供在线论文元数据检索及已保存查询结果回读接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.schemas.literature import LiteratureQuery, LiteratureResult
from app.services.literature_service import LiteratureService, LiteratureStore

router = APIRouter(prefix="/api/v1/literature", tags=["literature"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/search", response_model=LiteratureResult)
def search(
    query: LiteratureQuery, settings: SettingsDep, principal: PrincipalDep
) -> LiteratureResult:
    return LiteratureService(settings, principal.tenant_id).search(query)


@router.get("/queries/{query_id}", response_model=LiteratureResult)
def get_query(
    query_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> LiteratureResult:
    return LiteratureStore(tenant_data_dir(settings, principal.tenant_id)).load(query_id)
