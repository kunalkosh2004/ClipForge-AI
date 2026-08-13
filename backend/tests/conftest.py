import shutil
import subprocess
import uuid
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from clipforge.common.ids import uuid7
from clipforge.db import models as orm
from clipforge.db.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"

FFMPEG = shutil.which("ffmpeg")


def _make_video(path: Path, args: list[str]) -> Path:
    """Build a tiny test video with ffmpeg (colors / patterns / tone)."""
    cmd = ["ffmpeg", "-y", "-v", "error", *args, str(path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return path


@pytest.fixture(scope="session")
def scene_test_video(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """2s video: red then blue — one clear content-change boundary."""
    if FFMPEG is None:
        pytest.skip("ffmpeg not available")
    path = _make_video(
        tmp_path_factory.mktemp("media") / "scenes.mp4",
        [
            "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
    )
    yield path


@pytest.fixture(scope="session")
def static_video(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """2s static color — no motion."""
    if FFMPEG is None:
        pytest.skip("ffmpeg not available")
    yield _make_video(
        tmp_path_factory.mktemp("media") / "static.mp4",
        [
            "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
    )


@pytest.fixture(scope="session")
def moving_video(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """2s testsrc2 — continuously moving pattern."""
    if FFMPEG is None:
        pytest.skip("ffmpeg not available")
    yield _make_video(
        tmp_path_factory.mktemp("media") / "moving.mp4",
        [
            "-f", "lavfi", "-i", "testsrc2=s=320x240:d=2:r=15",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
    )


@pytest.fixture(scope="session")
def tone_video(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """2s 440Hz tone with a black frame — has audio."""
    if FFMPEG is None:
        pytest.skip("ffmpeg not available")
    yield _make_video(
        tmp_path_factory.mktemp("media") / "tone.mp4",
        [
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        ],
    )


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid7()


@pytest.fixture
def project_id() -> uuid.UUID:
    return uuid7()


@pytest.fixture
def video_id() -> uuid.UUID:
    return uuid7()


@pytest_asyncio.fixture
async def seed_user(session: AsyncSession, user_id: uuid.UUID) -> orm.User:
    user = orm.User(
        id=user_id,
        email="test@example.com",
        password_hash="hashed_password",
        full_name="Test User",
        role=orm.UserRole.USER,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    return user


@pytest_asyncio.fixture
async def seed_project(
    session: AsyncSession, seed_user: orm.User, project_id: uuid.UUID
) -> orm.Project:
    project = orm.Project(
        id=project_id,
        owner_id=seed_user.id,
        name="Test Project",
        status=orm.ProjectStatus.ACTIVE,
    )
    session.add(project)
    await session.commit()
    return project
