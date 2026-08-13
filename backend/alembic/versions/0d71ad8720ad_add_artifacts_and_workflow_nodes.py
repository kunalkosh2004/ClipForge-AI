"""add artifacts and workflow_nodes

Revision ID: 0d71ad8720ad
Revises: c1e2d3e4f5a6
Create Date: 2026-08-07 02:52:15.168286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d71ad8720ad'
down_revision: Union[str, None] = 'c1e2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'artifacts',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('video_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('version', sa.String(length=32), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('video_id', 'kind', name='uq_artifacts_video_kind'),
    )
    op.create_index('ix_artifacts_video_id', 'artifacts', ['video_id'])

    op.create_table(
        'workflow_nodes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('video_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='waiting'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('depends_on', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('queue', sa.String(length=32), nullable=False, server_default='default'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('video_id', 'kind', name='uq_workflow_nodes_video_kind'),
    )
    op.create_index('ix_workflow_nodes_video_id', 'workflow_nodes', ['video_id'])
    op.create_index('ix_workflow_nodes_status', 'workflow_nodes', ['status'])


def downgrade() -> None:
    op.drop_index('ix_workflow_nodes_status', table_name='workflow_nodes')
    op.drop_index('ix_workflow_nodes_video_id', table_name='workflow_nodes')
    op.drop_table('workflow_nodes')
    op.drop_index('ix_artifacts_video_id', table_name='artifacts')
    op.drop_table('artifacts')
