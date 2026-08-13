"""add editing_blueprint to analysis_results

Revision ID: d3e4f5a6b7c8
Revises: 0d71ad8720ad
Create Date: 2026-08-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = '0d71ad8720ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_results', sa.Column('editing_blueprint', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_results', 'editing_blueprint')
