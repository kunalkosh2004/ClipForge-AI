"""add editing_style to videos

Revision ID: c1e2d3e4f5a6
Revises: 9b90171115e1
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1e2d3e4f5a6'
down_revision: Union[str, None] = '9b90171115e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('editing_style', sa.String(length=2000), nullable=True))


def downgrade() -> None:
    op.drop_column('videos', 'editing_style')
