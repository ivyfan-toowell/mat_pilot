"""V0.10 section-aware RAG chunk provenance without deleting old vectors.

Revision ID: 20261109_0003
Revises: 20261109_0002
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20261109_0003"
down_revision: str | None = "20261109_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.core.config import get_settings
    from app.services.schema import apply_schema

    apply_schema(get_settings())


def downgrade() -> None:
    raise NotImplementedError("Scientific provenance migrations must not drop audit data.")
