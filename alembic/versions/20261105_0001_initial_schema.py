"""Initial MatPilot schema via apply_schema.

Revision ID: 20261105_0001
Revises:
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20261105_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.core.config import get_settings
    from app.services.schema import apply_schema

    apply_schema(get_settings())


def downgrade() -> None:
    raise NotImplementedError("Downgrade drops research data; restore from backup instead.")
