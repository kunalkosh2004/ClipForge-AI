import uuid

import pytest

from clipforge.common.errors import EntityNotFoundError, ForbiddenError, UserError
from clipforge.common.events import DomainEvent
from clipforge.common.pagination import PageRequest, PageResult
from clipforge.videos.application.schemas import CreateVideoRequest, ImportVideoRequest
from clipforge.videos.application.service import VideoService
from clipforge.videos.domain.entities import Project, Video


class FakeProjectRepo:
    def __init__(self) -> None:
        self._projects: dict[uuid.UUID, Project] = {}

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        return self._projects.get(project_id)

    async def create(self, project: Project) -> Project:
        self._projects[project.id] = project
        return project

    async def list_for_owner(
        self, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Project]:
        page = page or PageRequest()
        items = [p for p in self._projects.values() if p.owner_id == owner_id]
        return PageResult(items=items, total=len(items), limit=page.limit, offset=page.offset)

    async def delete(self, project_id: uuid.UUID) -> bool:
        return self._projects.pop(project_id, None) is not None


class FakeVideoRepo:
    def __init__(self) -> None:
        self._videos: dict[uuid.UUID, Video] = {}

    async def get_owned(self, video_id: uuid.UUID, owner_id: uuid.UUID) -> Video | None:
        v = self._videos.get(video_id)
        if v is None:
            return None
        return v

    async def get_by_id(self, video_id: uuid.UUID) -> Video | None:
        return self._videos.get(video_id)

    async def create(self, video: Video) -> Video:
        self._videos[video.id] = video
        return video

    async def update_status(self, video_id: uuid.UUID, status: str) -> Video | None:
        v = self._videos.get(video_id)
        if v is None:
            return None
        object.__setattr__(v, "status", status)
        return v

    async def update_editing_style(
        self, video_id: uuid.UUID, editing_style: str | None
    ) -> Video | None:
        v = self._videos.get(video_id)
        if v is None:
            return None
        object.__setattr__(v, "editing_style", editing_style)
        return v

    async def update_metadata(self, video_id: uuid.UUID, **kwargs: object) -> Video | None:
        return self._videos.get(video_id)

    async def list_for_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Video]:
        page = page or PageRequest()
        items = [v for v in self._videos.values() if v.project_id == project_id]
        return PageResult(items=items, total=len(items), limit=page.limit, offset=page.offset)

    async def delete(self, video_id: uuid.UUID) -> bool:
        return self._videos.pop(video_id, None) is not None


class FakeStorage:
    def __init__(self) -> None:
        self._exists_result = True

    async def put(self, key: str, data: object, content_type: str) -> None:
        pass

    async def get(self, key: str) -> bytes:
        return b""

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return self._exists_result

    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return f"https://storage.test/upload/{key}"

    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://storage.test/download/{key}"


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict, str]] = []

    def enqueue(self, task_name: str, payload: dict, queue: str = "default") -> None:
        self.enqueued.append((task_name, payload, queue))


class FakeEventBus:
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    async def list_events(
        self, aggregate_id: str | None = None, limit: int = 100
    ) -> list[DomainEvent]:
        return []

    async def read_after(
        self,
        cursor: str,
        aggregate_id: str | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        return []


@pytest.fixture
def repos() -> tuple[FakeProjectRepo, FakeVideoRepo, FakeStorage, FakeQueue, FakeEventBus]:
    return FakeProjectRepo(), FakeVideoRepo(), FakeStorage(), FakeQueue(), FakeEventBus()


@pytest.fixture
def service(repos: tuple) -> VideoService:
    projects, videos, storage, queue, events = repos
    return VideoService(
        projects=projects,
        videos=videos,
        storage=storage,
        queue=queue,
        events=events,
        media_queue="media",
    )


@pytest.mark.asyncio
async def test_create_project(service: VideoService) -> None:
    owner = uuid.uuid4()
    project = await service.create_project(owner, "My Project")
    assert project.name == "My Project"
    assert project.owner_id == owner


@pytest.mark.asyncio
async def test_list_projects(service: VideoService) -> None:
    owner = uuid.uuid4()
    await service.create_project(owner, "P1")
    await service.create_project(owner, "P2")
    result = await service.list_projects(owner)
    assert result.total == 2


@pytest.mark.asyncio
async def test_delete_project(service: VideoService) -> None:
    owner = uuid.uuid4()
    project = await service.create_project(owner, "To Delete")
    await service.delete_project(owner, project.id)


@pytest.mark.asyncio
async def test_delete_project_not_found(service: VideoService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.delete_project(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_start_upload(service: VideoService) -> None:
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = CreateVideoRequest(
        project_id=project.id,
        filename="test.mp4",
        content_type="video/mp4",
        size_bytes=1024,
    )
    result = await service.start_upload(owner, req)
    assert result.upload_url.startswith("https://")
    assert result.video_id is not None


@pytest.mark.asyncio
async def test_start_upload_wrong_project(service: VideoService) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = CreateVideoRequest(
        project_id=project.id,
        filename="test.mp4",
        content_type="video/mp4",
        size_bytes=1024,
    )
    with pytest.raises(ForbiddenError):
        await service.start_upload(other, req)


@pytest.mark.asyncio
async def test_start_upload_bad_mime(service: VideoService) -> None:
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = CreateVideoRequest(
        project_id=project.id,
        filename="test.txt",
        content_type="text/plain",
        size_bytes=1024,
    )
    with pytest.raises(UserError):
        await service.start_upload(owner, req)


@pytest.mark.asyncio
async def test_import_from_youtube(service: VideoService, repos: tuple) -> None:
    _, videos, storage, queue, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = ImportVideoRequest(
        project_id=project.id,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    result = await service.import_from_youtube(owner, req)
    assert result.status == "importing"
    assert result.video_id is not None
    assert len(queue.enqueued) == 1
    task_name, payload, _ = queue.enqueued[0]
    assert task_name == "youtube_import"
    assert str(result.video_id) in payload.values()


@pytest.mark.asyncio
async def test_import_from_youtube_bad_url(service: VideoService) -> None:
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = ImportVideoRequest(
        project_id=project.id,
        url="https://vimeo.com/12345",
    )
    with pytest.raises(UserError):
        await service.import_from_youtube(owner, req)


@pytest.mark.asyncio
async def test_import_from_youtube_wrong_project(service: VideoService) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = ImportVideoRequest(
        project_id=project.id,
        url="https://youtu.be/dQw4w9WgXcQ",
    )
    with pytest.raises(ForbiddenError):
        await service.import_from_youtube(other, req)


@pytest.mark.asyncio
async def test_import_stores_source_url(service: VideoService, repos: tuple) -> None:
    _, videos, storage, queue, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = ImportVideoRequest(
        project_id=project.id,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="My Favorite Video",
    )
    result = await service.import_from_youtube(owner, req)
    video = await videos.get_by_id(result.video_id)
    assert video is not None
    assert video.source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert video.original_filename == "My Favorite Video"
    assert video.status == "importing"


@pytest.mark.asyncio
async def test_complete_upload_stores_without_processing(
    service: VideoService, repos: tuple
) -> None:
    _, videos, storage, queue, events = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = CreateVideoRequest(
        project_id=project.id,
        filename="test.mp4",
        content_type="video/mp4",
        size_bytes=1024,
    )
    started = await service.start_upload(owner, req)
    storage._exists_result = True
    result = await service.complete_upload(owner, started.video_id)
    assert result.status == "uploaded"
    video = await videos.get_by_id(started.video_id)
    assert video is not None
    assert video.status == "uploaded"
    assert queue.enqueued == []
    assert len(events.published) == 1


@pytest.mark.asyncio
async def test_complete_upload_missing_object(service: VideoService, repos: tuple) -> None:
    _, videos, storage, _, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    req = CreateVideoRequest(
        project_id=project.id,
        filename="test.mp4",
        content_type="video/mp4",
        size_bytes=1024,
    )
    started = await service.start_upload(owner, req)
    storage._exists_result = False
    with pytest.raises(UserError):
        await service.complete_upload(owner, started.video_id)


@pytest.mark.asyncio
async def test_process_video_enqueues_pipeline(service: VideoService, repos: tuple) -> None:
    _, videos, storage, queue, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    video = await videos.create(
        Video(
            id=uuid.uuid4(),
            project_id=project.id,
            original_filename="clip.mp4",
            storage_key="videos/x/clip.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            status="uploaded",
        )
    )
    storage._exists_result = True
    await service.process_video(owner, video.id)
    assert (await videos.get_by_id(video.id)).status == "processing"
    tasks = [task_name for task_name, _, _ in queue.enqueued]
    assert "metadata_extraction" in tasks
    assert "start_intelligence" in tasks
    metadata = next(
        (payload for task, payload, _ in queue.enqueued if task == "metadata_extraction")
    )
    assert metadata == {
        "video_id": str(video.id),
        "storage_key": "videos/x/clip.mp4",
    }


@pytest.mark.asyncio
async def test_process_video_rejects_active_state(
    service: VideoService, repos: tuple
) -> None:
    _, videos, storage, queue, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    video = await videos.create(
        Video(
            id=uuid.uuid4(),
            project_id=project.id,
            original_filename="clip.mp4",
            storage_key="videos/x/clip.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            status="processing",
        )
    )
    storage._exists_result = True
    with pytest.raises(UserError):
        await service.process_video(owner, video.id)
    assert queue.enqueued == []


@pytest.mark.asyncio
async def test_update_video_sets_editing_style(service: VideoService, repos: tuple) -> None:
    _, videos, storage, _, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    video = await videos.create(
        Video(
            id=uuid.uuid4(),
            project_id=project.id,
            original_filename="clip.mp4",
            storage_key="videos/x/clip.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            status="uploaded",
        )
    )
    response = await service.update_video(owner, video.id, "  Fast-paced meme edits  ")
    assert response.editing_style == "Fast-paced meme edits"
    assert (await videos.get_by_id(video.id)).editing_style == "Fast-paced meme edits"
    cleared = await service.update_video(owner, video.id, None)
    assert cleared.editing_style is None


@pytest.mark.asyncio
async def test_start_intelligence_enqueues_on_media_queue(
    service: VideoService, repos: tuple
) -> None:
    _, videos, _, queue, _ = repos
    owner = uuid.uuid4()
    project = await service.create_project(owner, "P")
    video = await videos.create(
        Video(
            id=uuid.uuid4(),
            project_id=project.id,
            original_filename="clip.mp4",
            storage_key="videos/x/clip.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            status="ready",
        )
    )
    await service.start_intelligence(owner, video.id)
    assert len(queue.enqueued) == 1
    task_name, payload, queue_name = queue.enqueued[0]
    assert task_name == "start_intelligence"
    assert payload["video_id"] == str(video.id)
    assert queue_name == "media"


@pytest.mark.asyncio
async def test_start_intelligence_missing_video(service: VideoService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.start_intelligence(uuid.uuid4(), uuid.uuid4())
