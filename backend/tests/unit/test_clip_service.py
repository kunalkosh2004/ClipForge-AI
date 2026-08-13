import uuid

import pytest

from clipforge.clips.application.service import ClipService
from clipforge.clips.domain.entities import Clip
from clipforge.common.errors import EntityNotFoundError
from clipforge.common.pagination import PageRequest, PageResult


class FakeClipRepo:
    def __init__(self) -> None:
        self._clips: dict[uuid.UUID, Clip] = {}

    async def get_by_id(self, clip_id: uuid.UUID) -> Clip | None:
        return self._clips.get(clip_id)

    async def list_for_video(
        self, video_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        page = page or PageRequest()
        items = [c for c in self._clips.values() if c.video_id == video_id]
        sliced = items[page.offset : page.offset + page.limit]
        return PageResult(items=sliced, total=len(items), limit=page.limit, offset=page.offset)

    async def list_for_project(
        self, project_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        page = page or PageRequest()
        items = [c for c in self._clips.values() if c.project_id == project_id]
        sliced = items[page.offset : page.offset + page.limit]
        return PageResult(items=sliced, total=len(items), limit=page.limit, offset=page.offset)

    async def create(self, clip: Clip) -> Clip:
        self._clips[clip.id] = clip
        return clip

    async def count_for_video(self, video_id: uuid.UUID) -> int:
        return sum(1 for c in self._clips.values() if c.video_id == video_id)

    async def update_status(self, clip_id: uuid.UUID, status: str) -> Clip | None:
        c = self._clips.get(clip_id)
        if c is None:
            return None
        object.__setattr__(c, "status", status)
        return c

    async def update_storage(
        self, clip_id: uuid.UUID, storage_key: str, thumbnail_storage_key: str | None = None
    ) -> Clip | None:
        c = self._clips.get(clip_id)
        if c is None:
            return None
        object.__setattr__(c, "storage_key", storage_key)
        object.__setattr__(c, "status", "ready")
        if thumbnail_storage_key:
            object.__setattr__(c, "thumbnail_storage_key", thumbnail_storage_key)
        return c

    async def delete(self, clip_id: uuid.UUID) -> bool:
        return self._clips.pop(clip_id, None) is not None


class FakeStorage:
    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://storage.test/download/{key}"

    async def put(self, key: str, data: object, content_type: str) -> None:
        pass

    async def get(self, key: str) -> bytes:
        return b""

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return True

    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return f"https://storage.test/upload/{key}"


class FakeNotifier:
    async def publish(self, event: dict) -> None:
        pass


@pytest.fixture
def service() -> ClipService:
    return ClipService(clips=FakeClipRepo(), storage=FakeStorage(), notifier=FakeNotifier())


@pytest.mark.asyncio
async def test_create_clips_from_editing_plan(service: ClipService) -> None:
    vid = uuid.uuid4()
    proj = uuid.uuid4()
    plan = {
        "clips": [
            {"start": 10.0, "end": 20.0, "rationale": "First clip"},
            {"start": 30.0, "end": 45.0, "rationale": "Second clip"},
        ]
    }
    clips = await service.create_clips_from_editing_plan(vid, proj, plan)
    assert len(clips) == 2
    assert clips[0].start_seconds == 10.0
    assert clips[1].duration_seconds == 15.0


@pytest.mark.asyncio
async def test_create_clips_from_reference_format(service: ClipService) -> None:
    vid = uuid.uuid4()
    proj = uuid.uuid4()
    plan = {
        "preset": "storytelling",
        "thumbnail_text": "BIGGEST MISTAKE",
        "clips": [
            {
                "start_time": "01:20",
                "end_time": "01:52",
                "hook": "This mistake changed everything",
                "why_it_is_engaging": "Suspense.",
                "viral_score": 95,
                "emotion": "Surprise",
                "category": "Storytelling",
            },
        ],
    }
    clips = await service.create_clips_from_editing_plan(vid, proj, plan)
    assert len(clips) == 1
    assert clips[0].start_seconds == 80.0
    assert clips[0].end_seconds == 112.0
    assert clips[0].duration_seconds == 32.0
    assert clips[0].title == "This mistake changed everything"


@pytest.mark.asyncio
async def test_create_clips_empty_plan(service: ClipService) -> None:
    clips = await service.create_clips_from_editing_plan(uuid.uuid4(), uuid.uuid4(), {})
    assert len(clips) == 0


@pytest.mark.asyncio
async def test_get_clip(service: ClipService) -> None:
    vid = uuid.uuid4()
    proj = uuid.uuid4()
    clips = await service.create_clips_from_editing_plan(
        vid, proj, {"clips": [{"start": 0, "end": 5, "rationale": "test"}]}
    )
    found = await service.get_clip(clips[0].id)
    assert found.id == clips[0].id


@pytest.mark.asyncio
async def test_get_clip_not_found(service: ClipService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.get_clip(uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_clip(service: ClipService) -> None:
    vid = uuid.uuid4()
    clips = await service.create_clips_from_editing_plan(
        vid, uuid.uuid4(), {"clips": [{"start": 0, "end": 5}]}
    )
    await service.delete_clip(clips[0].id)
    with pytest.raises(EntityNotFoundError):
        await service.get_clip(clips[0].id)


@pytest.mark.asyncio
async def test_list_clips_for_video(service: ClipService) -> None:
    vid = uuid.uuid4()
    await service.create_clips_from_editing_plan(
        vid, uuid.uuid4(), {"clips": [{"start": 0, "end": 5}, {"start": 10, "end": 15}]}
    )
    result = await service.list_clips_for_video(vid)
    assert result.total == 2


@pytest.mark.asyncio
async def test_list_clips_pagination(service: ClipService) -> None:
    vid = uuid.uuid4()
    await service.create_clips_from_editing_plan(
        vid, uuid.uuid4(), {"clips": [{"start": i, "end": i + 1} for i in range(5)]}
    )
    result = await service.list_clips_for_video(vid, PageRequest(limit=2, offset=0))
    assert len(result.items) == 2
    assert result.total == 5
    assert result.has_more is True
