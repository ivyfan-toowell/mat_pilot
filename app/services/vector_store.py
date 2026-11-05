"""在 PostgreSQL 与 pgvector 中事务化保存向量索引（不含文献全文副本）。"""

from uuid import UUID

from app.core.config import LOCAL_TENANT_ID, Settings
from app.core.errors import ServiceError
from app.schemas.document import ParsedDocument
from app.schemas.retrieval import Chunk, SearchHit
from app.services.db import connect_postgres


class VectorStore:
    def __init__(self, settings: Settings, tenant_id: str = LOCAL_TENANT_ID) -> None:
        self.settings = settings
        self.tenant_id = tenant_id

    def connect(self):
        return connect_postgres(self.settings, register_pgvector=True)

    def verify_embedding_config(self) -> None:
        """Read-only compatibility check; does not create tables."""
        with self.connect() as conn:
            try:
                incompatible = conn.execute(
                    "SELECT 1 FROM mp_documents WHERE embedding_model <> %s "
                    "OR dimensions <> %s LIMIT 1",
                    (self.settings.embedding_model, self.settings.embedding_dimensions),
                ).fetchone()
                dimension = conn.execute("""SELECT format_type(a.atttypid, a.atttypmod) AS type
                    FROM pg_attribute a WHERE a.attrelid = 'mp_chunks'::regclass
                    AND a.attname = 'embedding'""").fetchone()["type"]
            except Exception as exc:
                raise ServiceError(
                    "schema_not_ready",
                    "数据库表未就绪，请启动时开启 SCHEMA_AUTO_APPLY 或执行迁移。",
                    503,
                ) from exc
            if incompatible or dimension != f"vector({self.settings.embedding_dimensions})":
                raise ServiceError(
                    "embedding_config_mismatch",
                    "向量模型或维度与知识库不一致，请使用独立数据库重建。",
                    409,
                )

    def replace(
        self, document: ParsedDocument, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        import numpy as np
        from psycopg.types.json import Jsonb

        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        self.verify_embedding_config()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT tenant_id FROM mp_documents WHERE document_id=%s",
                (document.document_id,),
            ).fetchone()
            if existing and existing["tenant_id"] != self.tenant_id:
                raise ServiceError(
                    "document_tenant_conflict",
                    "该文献已由其他租户索引，无法覆盖。",
                    409,
                )
            stub = Jsonb(
                {
                    "document_id": str(document.document_id),
                    "title": document.title,
                    "source": "index_registry",
                }
            )
            conn.execute(
                """INSERT INTO mp_documents(
                    document_id, parsed, embedding_model, dimensions, tenant_id)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT(document_id) DO UPDATE
                SET parsed=EXCLUDED.parsed, indexed_at=now(), tenant_id=EXCLUDED.tenant_id,
                    embedding_model=EXCLUDED.embedding_model, dimensions=EXCLUDED.dimensions
                WHERE mp_documents.tenant_id=EXCLUDED.tenant_id""",
                (
                    document.document_id,
                    stub,
                    self.settings.embedding_model,
                    self.settings.embedding_dimensions,
                    self.tenant_id,
                ),
            )
            conn.execute(
                "DELETE FROM mp_chunks WHERE document_id=%s AND tenant_id=%s",
                (document.document_id, self.tenant_id),
            )
            with conn.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO mp_chunks
                    (chunk_id,document_id,block_id,page_number,kind,text,title,
                     source_url,license,embedding,tenant_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        (
                            c.chunk_id,
                            c.document_id,
                            c.block_id,
                            c.page_number,
                            c.kind,
                            c.text,
                            c.title,
                            c.source_url,
                            c.license,
                            np.array(v, dtype=np.float32),
                            self.tenant_id,
                        )
                        for c, v in zip(chunks, vectors, strict=True)
                    ],
                )

    def search(
        self, vector: list[float], document_id: UUID | None, top_k: int, min_similarity: float
    ) -> list[SearchHit]:
        import numpy as np

        self.verify_embedding_config()
        query_vector = np.array(vector, dtype=np.float32)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT chunk_id,document_id,block_id,page_number,kind,
                text,title,source_url,license,1-(embedding <=> %s) AS similarity
                FROM mp_chunks WHERE tenant_id=%s
                AND (%s::uuid IS NULL OR document_id=%s)
                AND 1-(embedding <=> %s) >= %s ORDER BY embedding <=> %s LIMIT %s""",
                (
                    query_vector,
                    self.tenant_id,
                    document_id,
                    document_id,
                    query_vector,
                    min_similarity,
                    query_vector,
                    top_k,
                ),
            ).fetchall()
        return [SearchHit.model_validate(row) for row in rows]

    def list_chunks(self, document_id: UUID | None, limit: int) -> tuple[list[Chunk], bool]:
        """Bound the in-memory sparse corpus and expose truncation to callers."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT chunk_id,document_id,block_id,page_number,kind,
                text,title,source_url,license FROM mp_chunks
                WHERE tenant_id=%s AND (%s::uuid IS NULL OR document_id=%s)
                ORDER BY document_id, page_number, block_id, chunk_id LIMIT %s""",
                (self.tenant_id, document_id, document_id, limit + 1),
            ).fetchall()
        return [Chunk.model_validate(row) for row in rows[:limit]], len(rows) > limit
