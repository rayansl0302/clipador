"""enquadramento do rosto

Revision ID: 002_frame
Revises: 001_initial
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_frame"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("frame_x", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("frame_y", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("frame_w", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("frame_h", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "frame_h")
    op.drop_column("projects", "frame_w")
    op.drop_column("projects", "frame_y")
    op.drop_column("projects", "frame_x")
