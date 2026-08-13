"""add source_url to videos

Revision ID: a3f9c1e2d4b6
Revises: 8cefeb075c6c
Create Date: 2026-08-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1e2d4b6'
down_revision: Union[str, None] = '8cefeb075c6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('source_url', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column('videos', 'source_url')
