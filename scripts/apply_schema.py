"""Apply Postgres schema (DDL). Prefer Alembic in production; this wraps the same SQL."""

from app.core.config import get_settings
from app.services.schema import apply_schema


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("需要配置 DATABASE_URL")
    apply_schema(settings)
    print({"schema": "applied", "vector_hnsw": settings.vector_hnsw})


if __name__ == "__main__":
    main()
