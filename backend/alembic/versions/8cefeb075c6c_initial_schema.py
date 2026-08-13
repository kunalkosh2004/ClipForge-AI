"""initial schema

Revision ID: 8cefeb075c6c
Revises:
Create Date: 2026-08-04 11:05:22.156279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8cefeb075c6c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=True),
    sa.Column('role', sa.Enum('USER', 'ADMIN', name='userrole', native_enum=False), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table('projects',
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'ARCHIVED', name='projectstatus', native_enum=False), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)

    op.create_table('videos',
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=True),
    sa.Column('content_type', sa.String(length=120), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Enum('UPLOADING', 'PENDING', 'PROCESSING', 'ANALYZING', 'READY', 'FAILED', name='videostatus', native_enum=False), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    op.create_index(op.f('ix_videos_project_id'), 'videos', ['project_id'], unique=False)

    op.create_table('jobs',
    sa.Column('video_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('METADATA_EXTRACTION', 'AI_ANALYSIS', 'CLIP_EXTRACTION', 'RENDER', name='jobtype', native_enum=False), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', name='jobstatus', native_enum=False), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('dedupe_key', sa.String(length=255), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key')
    )
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index(op.f('ix_jobs_type'), 'jobs', ['type'], unique=False)
    op.create_index(op.f('ix_jobs_video_id'), 'jobs', ['video_id'], unique=False)

    op.create_table('transcripts',
    sa.Column('video_id', sa.UUID(), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('segments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('words', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('video_id'),
    )
    op.create_index(op.f('ix_transcripts_video_id'), 'transcripts', ['video_id'], unique=False)

    op.create_table('analysis_results',
    sa.Column('video_id', sa.UUID(), nullable=False),
    sa.Column('understanding', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('editing_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ai_model', sa.String(length=100), nullable=False),
    sa.Column('ai_cost_cents', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('video_id'),
    )
    op.create_index(op.f('ix_analysis_results_video_id'), 'analysis_results', ['video_id'], unique=False)

    op.create_table('clips',
    sa.Column('video_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('duration_seconds', sa.Float(), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('thumbnail_storage_key', sa.String(length=512), nullable=True),
    sa.Column('editing_plan_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Enum('PENDING', 'CUTTING', 'READY', 'FAILED',
                               name='clipstatus', native_enum=False), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_clips_video_id'), 'clips', ['video_id'], unique=False)
    op.create_index(op.f('ix_clips_project_id'), 'clips', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_clips_project_id'), table_name='clips')
    op.drop_index(op.f('ix_clips_video_id'), table_name='clips')
    op.drop_table('clips')
    op.execute("DROP TYPE IF EXISTS clipstatus")

    op.drop_index(op.f('ix_analysis_results_video_id'), table_name='analysis_results')
    op.drop_table('analysis_results')

    op.drop_index(op.f('ix_transcripts_video_id'), table_name='transcripts')
    op.drop_table('transcripts')

    op.drop_index(op.f('ix_jobs_video_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_type'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_table('jobs')
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS jobtype")

    op.drop_index(op.f('ix_videos_project_id'), table_name='videos')
    op.drop_table('videos')
    op.execute("DROP TYPE IF EXISTS videostatus")

    op.drop_index(op.f('ix_projects_owner_id'), table_name='projects')
    op.drop_table('projects')
    op.execute("DROP TYPE IF EXISTS projectstatus")

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS userrole")
