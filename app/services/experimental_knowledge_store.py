"""Tenant-scoped versioned experimental knowledge persisted in PostgreSQL.

Preserves legacy mp_experiments. Documents must already be owned by the tenant.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.experimental_knowledge import ExperimentalObservation
from app.services.db import connect_postgres


class ExperimentalKnowledgeStore:
    def __init__(self, settings: Settings, tenant_id: str):
        self.settings, self.tenant_id = settings, tenant_id

    def save(
        self, document_id: UUID, records: list[ExperimentalObservation], *, model: str = "unknown"
    ) -> UUID:
        if any(r.document_id != document_id or r.tenant_id != self.tenant_id for r in records):
            raise ServiceError("invalid_observation_scope", "文档或租户与实验记录不一致。", 422)
        if len({r.observation_id for r in records}) != len(records):
            raise ServiceError("duplicate_observation", "存在重复实验记录 ID。", 422)
        from psycopg.types.json import Jsonb

        run_id = uuid4()
        with connect_postgres(self.settings) as conn:
            owned = conn.execute(
                "SELECT 1 FROM mp_docs WHERE document_id=%s AND tenant_id=%s "
                "AND parsed->>'deleted_at' IS NULL",
                (document_id, self.tenant_id),
            ).fetchone()
            if not owned:
                raise ServiceError("document_not_found", "文献不存在或不属于当前租户。", 404)
            conn.execute(
                """INSERT INTO mp_knowledge_runs(run_id,tenant_id,document_id,model,status)
                   VALUES(%s,%s,%s,%s,'completed')""",
                (run_id, self.tenant_id, document_id, model),
            )
            # Replace only prior machine drafts; reviewed evidence remains immutable.
            conn.execute(
                """DELETE FROM mp_knowledge_observations
                   WHERE tenant_id=%s AND document_id=%s
                     AND verification_status='evidence_matched_needs_review'""",
                (self.tenant_id, document_id),
            )
            for record in records:
                payload = record.model_copy(update={"extraction_run_id": run_id})
                # Never overwrite accepted/rejected records by a new extraction.
                conn.execute(
                    """INSERT INTO mp_knowledge_observations
                       (observation_id,tenant_id,document_id,run_id,formula,property_name,
                        verification_status,observation)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(observation_id) DO NOTHING""",
                    (
                        payload.observation_id,
                        self.tenant_id,
                        document_id,
                        run_id,
                        payload.formula.value,
                        payload.property_name,
                        payload.verification_status,
                        Jsonb(payload.model_dump(mode="json")),
                    ),
                )
        return run_id

    def list(
        self,
        *,
        document_id: UUID | None = None,
        formula: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ExperimentalObservation]:
        if not 1 <= limit <= 200 or not 0 <= offset <= 100000:
            raise ServiceError("invalid_pagination", "分页参数超出范围。", 422)
        sql = """SELECT observation FROM mp_knowledge_observations
                 WHERE tenant_id=%s AND (%s::uuid IS NULL OR document_id=%s::uuid)
                   AND (%s::text IS NULL OR formula=%s::text)
                   AND (%s::text IS NULL OR verification_status=%s::text)
                   AND NOT EXISTS (SELECT 1 FROM mp_docs AS deleted_doc
                       WHERE deleted_doc.document_id=mp_knowledge_observations.document_id
                       AND deleted_doc.tenant_id=mp_knowledge_observations.tenant_id
                       AND deleted_doc.parsed->>'deleted_at' IS NOT NULL)
                 ORDER BY created_at DESC, observation_id LIMIT %s OFFSET %s"""
        params = (
            self.tenant_id,
            document_id,
            document_id,
            formula,
            formula,
            status,
            status,
            limit,
            offset,
        )
        with connect_postgres(self.settings) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ExperimentalObservation.model_validate(row["observation"]) for row in rows]

    def get(self, observation_id: UUID) -> ExperimentalObservation:
        with connect_postgres(self.settings) as conn:
            row = conn.execute(
                """SELECT observation FROM mp_knowledge_observations
                   WHERE tenant_id=%s AND observation_id=%s""",
                (self.tenant_id, observation_id),
            ).fetchone()
        if not row:
            raise ServiceError("observation_not_found", "未找到实验记录。", 404)
        return ExperimentalObservation.model_validate(row["observation"])

    def review(
        self, observation_id: UUID, decision: str, note: str, reviewer: str
    ) -> ExperimentalObservation:
        if decision not in ("human_verified", "rejected"):
            raise ServiceError("invalid_review", "只支持通过或拒绝。", 422)
        if not note.strip() or not reviewer.strip():
            raise ServiceError("invalid_review", "审核意见与审核人不能为空。", 422)
        from psycopg.types.json import Jsonb

        with connect_postgres(self.settings) as conn:
            row = conn.execute(
                """SELECT observation FROM mp_knowledge_observations
                   WHERE tenant_id=%s AND observation_id=%s FOR UPDATE""",
                (self.tenant_id, observation_id),
            ).fetchone()
            if not row:
                raise ServiceError("observation_not_found", "未找到实验记录。", 404)
            record = ExperimentalObservation.model_validate(row["observation"])
            if record.verification_status != "evidence_matched_needs_review":
                raise ServiceError("review_conflict", "该记录已经审核，禁止覆盖。", 409)
            # Human review must not modify cited source fields.
            record = record.model_copy(update={"verification_status": decision})
            conn.execute(
                """UPDATE mp_knowledge_observations
                   SET observation=%s, verification_status=%s, updated_at=now()
                   WHERE observation_id=%s AND tenant_id=%s""",
                (Jsonb(record.model_dump(mode="json")), decision, observation_id, self.tenant_id),
            )
            conn.execute(
                """INSERT INTO mp_knowledge_reviews
                   (review_id,tenant_id,observation_id,decision,note,reviewer)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (uuid4(), self.tenant_id, observation_id, decision, note.strip(), reviewer.strip()),
            )
        return record
