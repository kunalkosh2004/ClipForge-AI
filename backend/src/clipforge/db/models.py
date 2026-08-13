import enum
import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB as _PGJSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clipforge.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Portable JSON column: JSONB on PostgreSQL, plain JSON on SQLite (tests).
JSONB = sa.JSON().with_variant(_PGJSONB, "postgresql")


class UserRole(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class ProjectStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class VideoStatus(enum.StrEnum):
    UPLOADING = "uploading"
    IMPORTING = "importing"
    PENDING = "pending"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobType(enum.StrEnum):
    METADATA_EXTRACTION = "metadata_extraction"
    AI_ANALYSIS = "ai_analysis"
    CLIP_EXTRACTION = "clip_extraction"
    RENDER = "render"


class ClipStatus(enum.StrEnum):
    PENDING = "pending"
    CUTTING = "cutting"
    READY = "ready"
    FAILED = "failed"


class WorkflowNodeStatus(enum.StrEnum):
    WAITING = "waiting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.USER
    )
    is_active: Mapped[bool] = mapped_column(default=True)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False), default=ProjectStatus.ACTIVE
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    videos: Mapped[list["Video"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Video(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "videos"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    checksum: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    editing_style: Mapped[str | None] = mapped_column(String(2000))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False), default=VideoStatus.PENDING
    )

    project: Mapped[Project] = relationship(back_populates="videos")
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="video", uselist=False, cascade="all, delete-orphan"
    )
    analysis_result: Mapped["AnalysisResult | None"] = relationship(
        back_populates="video", uselist=False, cascade="all, delete-orphan"
    )
    clips: Mapped[list["Clip"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[JobType] = mapped_column(Enum(JobType, native_enum=False), index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.PENDING, index=True
    )
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    last_error: Mapped[str | None] = mapped_column(Text)

    video: Mapped[Video] = relationship(back_populates="jobs")


class Transcript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transcripts"

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True
    )
    language: Mapped[str] = mapped_column(String(10))
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    words: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    video: Mapped[Video] = relationship(back_populates="transcript")


class AnalysisResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_results"

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True
    )
    understanding: Mapped[dict[str, Any]] = mapped_column(JSONB)
    editing_plan: Mapped[dict[str, Any]] = mapped_column(JSONB)
    editing_blueprint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_model: Mapped[str] = mapped_column(String(100))
    ai_cost_cents: Mapped[int] = mapped_column(default=0)

    video: Mapped[Video] = relationship(back_populates="analysis_result")


class Clip(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clips"

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    render_storage_key: Mapped[str | None] = mapped_column(String(512))
    thumbnail_storage_key: Mapped[str | None] = mapped_column(String(512))
    editing_plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    format: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[ClipStatus] = mapped_column(
        Enum(ClipStatus, native_enum=False), default=ClipStatus.PENDING
    )
    rendered: Mapped[bool] = mapped_column(default=False)

    video: Mapped[Video] = relationship(back_populates="clips")


class AIModelUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_model_usage"

    date: Mapped[date] = mapped_column(Date, index=True)
    model: Mapped[str] = mapped_column(String(100))
    key_label: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(50))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True, index=True
    )


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Latest computed artifact for a (video, kind) pair.

    The JSON payload itself lives in storage (`storage_key`); this row is the
    cache index used by workers to skip recomputation when nothing changed.
    """

    __tablename__ = "artifacts"
    __table_args__ = (
        sa.UniqueConstraint("video_id", "kind", name="uq_artifacts_video_kind"),
    )

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)


class WorkflowNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A node in a video's intelligence workflow DAG.

    State advances via worker completion events. `depends_on` records the
    artifact kinds that must succeed first; the engine only enqueues nodes
    whose dependencies are satisfied, so the graph is data-driven and can be
    extended without touching the engine.
    """

    __tablename__ = "workflow_nodes"
    __table_args__ = (
        sa.UniqueConstraint("video_id", "kind", name="uq_workflow_nodes_video_kind"),
    )

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[WorkflowNodeStatus] = mapped_column(
        Enum(WorkflowNodeStatus, native_enum=False),
        default=WorkflowNodeStatus.WAITING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    depends_on: Mapped[list[str]] = mapped_column(JSONB, default=list)
    queue: Mapped[str] = mapped_column(String(32), default="default")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
