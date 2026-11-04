"""提供文献索引、知识库检索和带来源引用的问答接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.retrieval import AnswerResult, SearchRequest, SearchResult
from app.services.document_service import DocumentService
from app.services.rag_service import RagService

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/documents/{document_id}/index")
def index_document(document_id: UUID, settings: SettingsDep) -> dict:
    return RagService(settings).index(DocumentService(settings.data_dir).load(document_id))


@router.post("/search", response_model=SearchResult)
def search(request: SearchRequest, settings: SettingsDep) -> SearchResult:
    return RagService(settings).search(request)


@router.post("/answer", response_model=AnswerResult)
def answer(request: SearchRequest, settings: SettingsDep) -> AnswerResult:
    return RagService(settings).answer(request)
