"""提供本地 PDF 上传、解析结果和带页码原文证据查询接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.ingestion.extractor import ExperimentExtractor
from app.ingestion.pdf_parser import MAX_PDF_BYTES
from app.schemas.document import DocumentSummary, ParsedDocument
from app.schemas.experiment import ExtractionResult
from app.services.catalog_service import list_documents
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/documents", tags=["documents"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("", response_model=list[DocumentSummary])
def document_catalog(
    settings: SettingsDep, limit: Annotated[int, Query(ge=1, le=100)] = 100
) -> list[DocumentSummary]:
    return list_documents(settings.data_dir, limit)


@router.post("", response_model=ParsedDocument)
def upload_pdf(
    file: UploadFile,
    settings: SettingsDep,
    source_url: Annotated[str | None, Form()] = None,
    license_name: Annotated[str | None, Form()] = None,
) -> ParsedDocument:
    data = file.file.read(MAX_PDF_BYTES + 1)
    return DocumentService(settings.data_dir).ingest(
        data, file.filename or "paper.pdf", source_url, license_name
    )


@router.get("/{document_id}", response_model=ParsedDocument)
def get_document(document_id: UUID, settings: SettingsDep) -> ParsedDocument:
    return DocumentService(settings.data_dir).load(document_id)


@router.get("/{document_id}/experiments", response_model=ExtractionResult)
def get_experiments(document_id: UUID, settings: SettingsDep) -> ExtractionResult:
    try:
        return ExtractionResult.model_validate_json(
            (settings.data_dir / "documents" / str(document_id) / "experiments.json").read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        raise ServiceError(
            "experiments_not_found", "该文献尚无已保存的实验提取记录。", 404
        ) from None


@router.post("/{document_id}/extract", response_model=ExtractionResult)
def extract_experiments(document_id: UUID, settings: SettingsDep) -> ExtractionResult:
    document = DocumentService(settings.data_dir).load(document_id)
    return ExperimentExtractor(settings).extract(document)
