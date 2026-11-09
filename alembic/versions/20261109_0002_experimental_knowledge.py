"""Additive V0.9 experimental knowledge schema.

Revision ID: 20261109_0002
Revises: 20261105_0001

Both initial and upgrade paths invoke the idempotent apply_schema routine.
No destructive downgrade is offered for scientific audit/history tables.
"""
from __future__ import annotations
from collections.abc import Sequence

revision: str = "20261109_0002"
down_revision: str | None = "20261105_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    from app.core.config import get_settings
    from app.services.schema import apply_schema
    apply_schema(get_settings())

def downgrade() -> None:
    raise NotImplementedError("Do not drop scientific evidence. Restore from a verified backup.")
