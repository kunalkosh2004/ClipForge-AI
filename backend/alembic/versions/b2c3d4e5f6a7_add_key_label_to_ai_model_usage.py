"""add key label to ai model usage

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_model_usage",
        sa.Column("key_label", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_ai_model_usage_key_label", "ai_model_usage", ["key_label"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_model_usage_key_label", table_name="ai_model_usage")
    op.drop_column("ai_model_usage", "key_label")
