"""保存 PDF 原件；元数据以 Postgres 为 SSOT（未配置数据库时回退本地 JSON）。"""

import json
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import LOCAL_TENANT_ID, Settings
from app.core.errors import ServiceError
from app.ingestion.pdf_parser import MAX_PDF_BYTES, as_markdown, parse_pdf
from app.schemas.document import ParsedDocument
from app.schemas.experiment import ExtractionResult
from app.services.document_store import DocumentStore


class DocumentService:
    def __init__(
        self,
        data_dir: Path,
        settings: Settings | None = None,
        tenant_id: str = LOCAL_TENANT_ID,
    ) -> None:
        self.directory = data_dir / "documents"
        self.settings = settings
        self.tenant_id = tenant_id
        self.store = (
            DocumentStore(settings, tenant_id)
            if settings is not None and settings.database_url
            else None
        )

    def ingest(
        self,
        data: bytes,
        filename: str,
        source_url: str | None = None,
        license_name: str | None = None,
    ) -> ParsedDocument:
        if len(data) > MAX_PDF_BYTES:
            raise ServiceError("file_too_large", "PDF 不能超过 30 MB。", 413)
        if not data.startswith(b"%PDF-"):
            raise ServiceError("invalid_pdf", "文件内容不是有效的 PDF。", 422)
        document_id = uuid4()
        folder = self.directory / str(document_id)
        folder.mkdir(parents=True)
        original = folder / "original.pdf"
        original.write_bytes(data)
        try:
            document = parse_pdf(original, document_id, filename.replace("\\", "/").split("/")[-1])
            document.source_url = source_url
            document.license = license_name
            self._persist_document(document, folder)
            return document
        except ServiceError as exc:
            (folder / "failure.json").write_text(
                json.dumps({"document_id": str(document_id), "status": "failed", "code": exc.code}),
                encoding="utf-8",
            )
            raise

    def load(self, document_id: UUID) -> ParsedDocument:
        # With DATABASE_URL, Postgres is SSOT — do not silently fall back to stale JSON.
        if self.store is not None:
            return self.store.get(document_id)
        try:
            return ParsedDocument.model_validate_json(
                (self.directory / str(document_id) / "parsed.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise ServiceError("document_not_found", "未找到已解析的文献。", 404) from exc

    def load_experiments(self, document_id: UUID) -> ExtractionResult:
        if self.store is not None:
            return self.store.get_experiments(document_id)
        try:
            return ExtractionResult.model_validate_json(
                (self.directory / str(document_id) / "experiments.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            raise ServiceError(
                "experiments_not_found", "该文献尚无已保存的实验提取记录。", 404
            ) from None

    def save_experiments(self, result: ExtractionResult, *, replace: bool = True) -> None:
        folder = self.directory / str(result.document_id)
        folder.mkdir(parents=True, exist_ok=True)
        if self.store is not None:
            if not replace and self.store.has_experiments(result.document_id):
                return
            self.store.save_experiments(result)
            return
        path = folder / "experiments.json"
        if not replace and path.exists():
            return
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    def has_experiments(self, document_id: UUID) -> bool:
        if self.store is not None:
            return self.store.has_experiments(document_id)
        return (self.directory / str(document_id) / "experiments.json").is_file()

    def _persist_document(self, document: ParsedDocument, folder: Path) -> None:
        (folder / "document.md").write_text(as_markdown(document), encoding="utf-8")
        if self.store is not None:
            self.store.upsert(document)
            return
        (folder / "parsed.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
