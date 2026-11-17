"""canal do vídeo de origem

Revision ID: 003_channel
Revises: 002_frame
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_channel"
down_revision: str | None = "002_frame"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("channel", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "channel")
