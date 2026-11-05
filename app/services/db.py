"""共享 PostgreSQL 连接，供文献元数据与向量库使用。"""

from app.core.config import Settings
from app.core.errors import ServiceError


def connect_postgres(settings: Settings, *, register_pgvector: bool = False):
    if not settings.database_url:
        raise ServiceError("database_not_configured", "请配置 DATABASE_URL 并启动数据库。", 503)
    try:
        import psycopg
        from psycopg.rows import dict_row

        url = settings.database_url.get_secret_value().replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        conn = psycopg.connect(url, connect_timeout=5, row_factory=dict_row)
        if register_pgvector:
            try:
                from pgvector.psycopg import register_vector

                register_vector(conn)
            except Exception:
                conn.close()
                raise
        return conn
    except ImportError as exc:
        raise ServiceError("database_driver_missing", "请安装 postgres 可选依赖。", 503) from exc
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError(
            "database_unavailable", "无法连接数据库，请检查服务和初始化。", 503
        ) from exc
