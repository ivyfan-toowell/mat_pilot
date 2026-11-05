"""数据库 DDL 仅在启动或迁移脚本中执行，不在业务请求路径调用。"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.services.db import connect_postgres

logger = logging.getLogger(__name__)


def apply_schema(settings: Settings) -> None:
    """Create/upgrade tables once. Safe to call repeatedly (IF NOT EXISTS)."""
    with connect_postgres(settings, register_pgvector=True) as conn:
        from psycopg import sql

        conn.execute("""CREATE TABLE IF NOT EXISTS mp_docs (
            document_id uuid PRIMARY KEY,
            tenant_id text NOT NULL,
            parsed jsonb NOT NULL,
            has_experiments boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now())""")
        conn.execute("""CREATE TABLE IF NOT EXISTS mp_experiments (
            document_id uuid PRIMARY KEY
                REFERENCES mp_docs(document_id) ON DELETE CASCADE,
            tenant_id text NOT NULL,
            extraction jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now())""")
        conn.execute("""CREATE TABLE IF NOT EXISTS mp_documents (
            document_id uuid PRIMARY KEY,
            parsed jsonb NOT NULL DEFAULT '{}'::jsonb,
            embedding_model text NOT NULL,
            dimensions integer NOT NULL,
            indexed_at timestamptz NOT NULL DEFAULT now(),
            tenant_id text NOT NULL DEFAULT 'local')""")
        conn.execute(
            sql.SQL("""CREATE TABLE IF NOT EXISTS mp_chunks (
            chunk_id uuid PRIMARY KEY,
            document_id uuid NOT NULL REFERENCES mp_documents ON DELETE CASCADE,
            block_id text NOT NULL, page_number integer NOT NULL,
            kind text NOT NULL, text text NOT NULL, title text NOT NULL,
            source_url text, license text, embedding vector({}),
            tenant_id text NOT NULL DEFAULT 'local')""").format(
                sql.Literal(settings.embedding_dimensions)
            )
        )
        for statement in (
            "ALTER TABLE mp_documents ADD COLUMN IF NOT EXISTS tenant_id text "
            "NOT NULL DEFAULT 'local'",
            "ALTER TABLE mp_chunks ADD COLUMN IF NOT EXISTS tenant_id text "
            "NOT NULL DEFAULT 'local'",
            "CREATE INDEX IF NOT EXISTS mp_docs_tenant ON mp_docs(tenant_id)",
            "CREATE INDEX IF NOT EXISTS mp_experiments_tenant ON mp_experiments(tenant_id)",
            "CREATE INDEX IF NOT EXISTS mp_chunks_document ON mp_chunks(document_id)",
            "CREATE INDEX IF NOT EXISTS mp_documents_tenant ON mp_documents(tenant_id)",
            "CREATE INDEX IF NOT EXISTS mp_chunks_tenant ON mp_chunks(tenant_id)",
        ):
            conn.execute(statement)
        if settings.vector_hnsw:
            conn.execute(
                """CREATE INDEX IF NOT EXISTS mp_chunks_embedding_hnsw
                ON mp_chunks USING hnsw (embedding vector_cosine_ops)"""
            )
    logger.info("database schema applied vector_hnsw=%s", settings.vector_hnsw)
