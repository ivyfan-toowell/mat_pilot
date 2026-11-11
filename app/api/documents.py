"""提供本地 PDF 上传、解析结果和带页码原文证据查询接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from app.core.auth import PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.ingestion.extractor import ExperimentExtractor
from app.ingestion.pdf_parser import MAX_PDF_BYTES
from app.schemas.document import (
    DocumentCatalogPage,
    DocumentMetadataUpdate,
    DocumentStatus,
    DocumentSummary,
    ParsedDocument,
)
from app.schemas.experiment import ExtractionResult
from app.services.catalog_service import document_page, list_documents
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


@router.get("/catalog", response_model=DocumentCatalogPage)
def paged_document_catalog(
    settings: SettingsDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
    q: Annotated[str, Query(max_length=200)] = "",
    deleted: bool = False,
) -> DocumentCatalogPage:
    return document_page(
        tenant_data_dir(settings, principal.tenant_id),
        limit,
        settings,
        principal.tenant_id,
        offset=offset,
        query=q.strip(),
        deleted=deleted,
    )


@router.delete("/{document_id}", response_model=DocumentStatus)
def delete_document(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> DocumentStatus:
    document = _docs(settings, principal.tenant_id).set_deleted(document_id, deleted=True)
    return DocumentStatus(document_id=document.document_id, deleted_at=document.deleted_at)


@router.post("/{document_id}/restore", response_model=DocumentStatus)
def restore_document(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> DocumentStatus:
    document = _docs(settings, principal.tenant_id).set_deleted(document_id, deleted=False)
    return DocumentStatus(document_id=document.document_id, deleted_at=document.deleted_at)


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


@router.patch("/{document_id}/metadata", response_model=ParsedDocument)
def update_document_metadata(
    document_id: UUID,
    metadata: DocumentMetadataUpdate,
    settings: SettingsDep,
    principal: PrincipalDep,
) -> ParsedDocument:
    return _docs(settings, principal.tenant_id).update_metadata(document_id, metadata)


@router.post("/{document_id}/extract", response_model=ExtractionResult)
def extract_experiments(
    document_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> ExtractionResult:
    document = _docs(settings, principal.tenant_id).load(document_id)
    return ExperimentExtractor(settings, principal.tenant_id).extract(document)
