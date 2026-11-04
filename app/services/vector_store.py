"""在 PostgreSQL 与 pgvector 中事务化保存文献和向量，并提供检索。"""

from uuid import UUID

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.document import ParsedDocument
from app.schemas.retrieval import Chunk, SearchHit


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self):
        if not self.settings.database_url:
            raise ServiceError("database_not_configured", "请配置 DATABASE_URL 并启动数据库。", 503)
        try:
            import psycopg
            from pgvector.psycopg import register_vector
            from psycopg.rows import dict_row

            url = self.settings.database_url.get_secret_value().replace(
                "postgresql+psycopg://", "postgresql://", 1
            )
            conn = psycopg.connect(url, connect_timeout=5, row_factory=dict_row)
            try:
                register_vector(conn)
            except Exception:
                conn.close()
                raise
            return conn
        except ImportError as exc:
            raise ServiceError(
                "database_driver_missing", "请安装 postgres 可选依赖。", 503
            ) from exc
        except Exception as exc:
            raise ServiceError(
                "database_unavailable", "无法连接 pgvector，请检查数据库服务和初始化。", 503
            ) from exc

    def initialize(self) -> None:
        # Dimensions are validated integers; identifiers/values are never interpolated from input.
        with self.connect() as conn:
            from psycopg import sql

            conn.execute("""CREATE TABLE IF NOT EXISTS mp_documents (
                document_id uuid PRIMARY KEY, parsed jsonb NOT NULL,
                embedding_model text NOT NULL, dimensions integer NOT NULL,
                indexed_at timestamptz NOT NULL DEFAULT now())""")
            conn.execute(
                sql.SQL("""CREATE TABLE IF NOT EXISTS mp_chunks (
                chunk_id uuid PRIMARY KEY,
                document_id uuid NOT NULL REFERENCES mp_documents ON DELETE CASCADE,
                block_id text NOT NULL, page_number integer NOT NULL,
                kind text NOT NULL, text text NOT NULL, title text NOT NULL,
                source_url text, license text, embedding vector({}))""").format(
                    sql.Literal(self.settings.embedding_dimensions)
                )
            )
            conn.execute("CREATE INDEX IF NOT EXISTS mp_chunks_document ON mp_chunks(document_id)")
            # Refuse silently mixing incompatible models or dimensions in the same corpus.
            incompatible = conn.execute(
                "SELECT 1 FROM mp_documents WHERE embedding_model <> %s "
                "OR dimensions <> %s LIMIT 1",
                (self.settings.embedding_model, self.settings.embedding_dimensions),
            ).fetchone()
            dimension = conn.execute("""SELECT format_type(a.atttypid, a.atttypmod) AS type
                FROM pg_attribute a WHERE a.attrelid = 'mp_chunks'::regclass
                AND a.attname = 'embedding'""").fetchone()["type"]
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
        self.initialize()
        with self.connect() as conn:
            # Row lock serializes concurrent replacement of the same document.
            conn.execute(
                """INSERT INTO mp_documents(document_id, parsed, embedding_model, dimensions)
                VALUES (%s,%s,%s,%s) ON CONFLICT(document_id) DO UPDATE
                SET parsed=EXCLUDED.parsed, indexed_at=now()""",
                (
                    document.document_id,
                    Jsonb(document.model_dump(mode="json")),
                    self.settings.embedding_model,
                    self.settings.embedding_dimensions,
                ),
            )
            conn.execute("DELETE FROM mp_chunks WHERE document_id=%s", (document.document_id,))
            with conn.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO mp_chunks
                    (chunk_id,document_id,block_id,page_number,kind,text,title,source_url,license,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
                        )
                        for c, v in zip(chunks, vectors, strict=True)
                    ],
                )

    def search(
        self, vector: list[float], document_id: UUID | None, top_k: int, min_similarity: float
    ) -> list[SearchHit]:
        import numpy as np

        self.initialize()
        query_vector = np.array(vector, dtype=np.float32)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT chunk_id,document_id,block_id,page_number,kind,
                text,title,source_url,license,1-(embedding <=> %s) AS similarity
                FROM mp_chunks WHERE (%s::uuid IS NULL OR document_id=%s)
                AND 1-(embedding <=> %s) >= %s ORDER BY embedding <=> %s LIMIT %s""",
                (
                    query_vector,
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
                WHERE (%s::uuid IS NULL OR document_id=%s)
                ORDER BY document_id, page_number, block_id, chunk_id LIMIT %s""",
                (document_id, document_id, limit + 1),
            ).fetchall()
        return [Chunk.model_validate(row) for row in rows[:limit]], len(rows) > limit
