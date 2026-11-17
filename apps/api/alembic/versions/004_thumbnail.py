"""miniatura do vídeo de origem

Revision ID: 004_thumbnail
Revises: 003_channel
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_thumbnail"
down_revision: str | None = "003_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("thumbnail_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "thumbnail_url")
