"""提供文献索引、知识库检索和带来源引用的问答接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.schemas.retrieval import AnswerResult, IndexResult, SearchRequest, SearchResult
from app.services.document_service import DocumentService
from app.services.rag_service import RagService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/documents/{document_id}/index", response_model=IndexResult)
def index_document(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> IndexResult:
    document = DocumentService(
        tenant_data_dir(settings, principal.tenant_id), settings, principal.tenant_id
    ).load(document_id)
    return IndexResult.model_validate(RagService(settings, principal.tenant_id).index(document))


@router.post("/search", response_model=SearchResult)
def search(
    request: SearchRequest, settings: SettingsDep, principal: PrincipalDep
) -> SearchResult:
    return RagService(settings, principal.tenant_id).search(request)


@router.post("/answer", response_model=AnswerResult)
def answer(
    request: SearchRequest, settings: SettingsDep, principal: PrincipalDep
) -> AnswerResult:
    return RagService(settings, principal.tenant_id).answer(request)
