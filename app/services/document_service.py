"""保存 PDF 原件、解析状态、Markdown 和结构化证据，支持结果回读。"""

import json
from pathlib import Path
from uuid import UUID, uuid4

from app.core.errors import ServiceError
from app.ingestion.pdf_parser import MAX_PDF_BYTES, as_markdown, parse_pdf
from app.schemas.document import ParsedDocument


class DocumentService:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "documents"

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
            (folder / "parsed.json").write_text(
                document.model_dump_json(indent=2), encoding="utf-8"
            )
            (folder / "document.md").write_text(as_markdown(document), encoding="utf-8")
            return document
        except ServiceError as exc:
            (folder / "failure.json").write_text(
                json.dumps({"document_id": str(document_id), "status": "failed", "code": exc.code}),
                encoding="utf-8",
            )
            raise

    def load(self, document_id: UUID) -> ParsedDocument:
        try:
            return ParsedDocument.model_validate_json(
                (self.directory / str(document_id) / "parsed.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise ServiceError("document_not_found", "未找到已解析的文献。", 404) from exc
