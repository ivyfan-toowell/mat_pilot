"""提供本地 PDF 上传、解析结果和带页码原文证据查询接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from app.core.auth import PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.ingestion.extractor import ExperimentExtractor
from app.ingestion.pdf_parser import MAX_PDF_BYTES
from app.schemas.document import DocumentSummary, ParsedDocument
from app.schemas.experiment import ExtractionResult
from app.services.catalog_service import list_documents
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _docs(settings: Settings, tenant_id: str) -> DocumentService:
    return DocumentService(tenant_data_dir(settings, tenant_id), settings, tenant_id)


@router.get("", response_model=list[DocumentSummary])
def document_catalog(
    settings: SettingsDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[DocumentSummary]:
    return list_documents(
        tenant_data_dir(settings, principal.tenant_id),
        limit,
        settings,
        principal.tenant_id,
    )


@router.post("", response_model=ParsedDocument)
def upload_pdf(
    file: UploadFile,
    settings: SettingsDep,
    principal: PrincipalDep,
    source_url: Annotated[str | None, Form()] = None,
    license_name: Annotated[str | None, Form()] = None,
) -> ParsedDocument:
    data = file.file.read(MAX_PDF_BYTES + 1)
    return _docs(settings, principal.tenant_id).ingest(
        data, file.filename or "paper.pdf", source_url, license_name
    )


@router.get("/{document_id}", response_model=ParsedDocument)
def get_document(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> ParsedDocument:
    return _docs(settings, principal.tenant_id).load(document_id)


@router.get("/{document_id}/experiments", response_model=ExtractionResult)
def get_experiments(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> ExtractionResult:
    return _docs(settings, principal.tenant_id).load_experiments(document_id)


@router.post("/{document_id}/extract", response_model=ExtractionResult)
def extract_experiments(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> ExtractionResult:
    document = _docs(settings, principal.tenant_id).load(document_id)
    return ExperimentExtractor(settings, principal.tenant_id).extract(document)
