"""add format to clips

Revision ID: 37247df92cad
Revises: 85e4ed265c09
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "37247df92cad"
down_revision: Union[str, None] = "85e4ed265c09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("format", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("clips", "format")
