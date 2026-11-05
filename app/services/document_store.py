"""文献与实验提取元数据的 Postgres 单一事实来源。"""

from uuid import UUID

from app.core.config import LOCAL_TENANT_ID, Settings
from app.core.errors import ServiceError
from app.schemas.document import DocumentSummary, ParsedDocument
from app.schemas.experiment import ExtractionResult
from app.services.db import connect_postgres


class DocumentStore:
    def __init__(self, settings: Settings, tenant_id: str = LOCAL_TENANT_ID) -> None:
        self.settings = settings
        self.tenant_id = tenant_id

    def connect(self):
        return connect_postgres(self.settings)

    def upsert(self, document: ParsedDocument) -> None:
        from psycopg.types.json import Jsonb

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT tenant_id FROM mp_docs WHERE document_id=%s", (document.document_id,)
            ).fetchone()
            if existing and existing["tenant_id"] != self.tenant_id:
                raise ServiceError(
                    "document_tenant_conflict", "该文献已由其他租户保存，无法覆盖。", 409
                )
            conn.execute(
                """INSERT INTO mp_docs(document_id, tenant_id, parsed, has_experiments)
                VALUES (%s,%s,%s,false)
                ON CONFLICT(document_id) DO UPDATE
                SET parsed=EXCLUDED.parsed, updated_at=now(), tenant_id=EXCLUDED.tenant_id
                WHERE mp_docs.tenant_id=EXCLUDED.tenant_id""",
                (document.document_id, self.tenant_id, Jsonb(document.model_dump(mode="json"))),
            )

    def get(self, document_id: UUID) -> ParsedDocument:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT parsed FROM mp_docs WHERE document_id=%s AND tenant_id=%s",
                (document_id, self.tenant_id),
            ).fetchone()
        if not row:
            raise ServiceError("document_not_found", "未找到已解析的文献。", 404)
        return ParsedDocument.model_validate(row["parsed"])

    def list(self, limit: int = 100) -> list[DocumentSummary]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT parsed, has_experiments FROM mp_docs
                WHERE tenant_id=%s
                ORDER BY (parsed->>'parsed_at') DESC NULLS LAST
                LIMIT %s""",
                (self.tenant_id, limit),
            ).fetchall()
        records = []
        for row in rows:
            document = ParsedDocument.model_validate(row["parsed"])
            records.append(
                DocumentSummary(**document.model_dump(), has_experiments=row["has_experiments"])
            )
        return records

    def save_experiments(self, result: ExtractionResult) -> None:
        from psycopg.types.json import Jsonb

        with self.connect() as conn:
            owned = conn.execute(
                "SELECT 1 FROM mp_docs WHERE document_id=%s AND tenant_id=%s",
                (result.document_id, self.tenant_id),
            ).fetchone()
            if not owned:
                raise ServiceError("document_not_found", "未找到已解析的文献。", 404)
            conn.execute(
                """INSERT INTO mp_experiments(document_id, tenant_id, extraction)
                VALUES (%s,%s,%s)
                ON CONFLICT(document_id) DO UPDATE
                SET extraction=EXCLUDED.extraction, updated_at=now()
                WHERE mp_experiments.tenant_id=EXCLUDED.tenant_id""",
                (result.document_id, self.tenant_id, Jsonb(result.model_dump(mode="json"))),
            )
            conn.execute(
                "UPDATE mp_docs SET has_experiments=true, updated_at=now() "
                "WHERE document_id=%s AND tenant_id=%s",
                (result.document_id, self.tenant_id),
            )

    def get_experiments(self, document_id: UUID) -> ExtractionResult:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT extraction FROM mp_experiments WHERE document_id=%s AND tenant_id=%s",
                (document_id, self.tenant_id),
            ).fetchone()
        if not row:
            raise ServiceError(
                "experiments_not_found", "该文献尚无已保存的实验提取记录。", 404
            )
        return ExtractionResult.model_validate(row["extraction"])

    def has_experiments(self, document_id: UUID) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT has_experiments FROM mp_docs WHERE document_id=%s AND tenant_id=%s",
                (document_id, self.tenant_id),
            ).fetchone()
        return bool(row and row["has_experiments"])
