import io
import uuid
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from clipforge.artifacts.domain.entities import Artifact
from clipforge.artifacts.domain.ports import ArtifactRepository, ArtifactStore
from clipforge.common.pagination import PageRequest, PageResult
from clipforge.common.ports import StorageProvider
from clipforge.intelligence.application.service import CACHED, COMPUTED, IntelligenceService
from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.videos.domain.entities import Video
from clipforge.videos.domain.ports import VideoRepository


class FakeStorage(StorageProvider):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        self.objects[key] = data.read()

    async def get(self, key: str) -> BinaryIO:
        return io.BytesIO(self.objects[key])

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return f"https://upload/{key}"

    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://download/{key}"


class FakeArtifactStore(ArtifactStore):
    def __init__(self) -> None:
        self.payloads: dict[tuple[uuid.UUID, str], tuple[str, dict[str, Any]]] = {}

    async def write(
        self, video_id: uuid.UUID, kind: str, payload: dict[str, Any], version: str
    ) -> Artifact:
        self.payloads[(video_id, kind)] = (version, payload)
        return Artifact(
            video_id=video_id,
            kind=kind,
            version=version,
            storage_key=f"k/{kind}.json",
            checksum="abc",
        )

    async def read_payload(self, video_id: uuid.UUID, kind: str) -> dict[str, Any] | None:
        entry = self.payloads.get((video_id, kind))
        return entry[1] if entry else None

    async def exists(self, video_id: uuid.UUID, kind: str) -> bool:
        return (video_id, kind) in self.payloads


class FakeArtifactRepo(ArtifactRepository):
    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str], Artifact] = {}

    async def create(self, artifact: Artifact) -> Artifact:
        self.rows[(artifact.video_id, artifact.kind)] = artifact
        return artifact

    async def get_latest(self, video_id: uuid.UUID, kind: str) -> Artifact | None:
        return self.rows.get((video_id, kind))

    async def list_for_video(self, video_id: uuid.UUID) -> list[Artifact]:
        return [a for (v, _), a in self.rows.items() if v == video_id]

    async def delete_for_video(self, video_id: uuid.UUID) -> int:
        before = len(self.rows)
        self.rows = {k: v for (v, _), (k, v) in self.rows.items() if v != video_id}
        return before - len(self.rows)


class FakeVideoRepo(VideoRepository):
    def __init__(self, video: Video | None) -> None:
        self.video = video

    async def get_owned(self, video_id: uuid.UUID, owner_id: uuid.UUID) -> Video | None:
        return self.video

    async def get_by_id(self, video_id: uuid.UUID) -> Video | None:
        return self.video

    async def create(self, video: Video) -> Video:
        return video

    async def update_status(self, video_id: uuid.UUID, status: str) -> Video | None:
        return self.video

    async def update_editing_style(
        self, video_id: uuid.UUID, editing_style: str | None
    ) -> Video | None:
        return self.video

    async def update_metadata(
        self,
        video_id: uuid.UUID,
        *,
        checksum: str,
        size_bytes: int,
        duration_seconds: float | None,
        metadata_json: dict[str, Any],
        status: str,
    ) -> Video | None:
        return self.video

    async def update_imported(
        self,
        video_id: uuid.UUID,
        *,
        original_filename: str,
        checksum: str,
        size_bytes: int,
        duration_seconds: float | None,
        metadata_json: dict[str, Any],
        status: str,
    ) -> Video | None:
        return self.video

    async def list_for_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Video]:
        page_number = page.page if page else 1
        per_page = page.per_page if page else 20
        return PageResult(items=[], total=0, page=page_number, per_page=per_page)

    async def delete(self, video_id: uuid.UUID) -> bool:
        return True


class StubWorker(IntelligenceWorker):
    kind = "stub"
    version = "stub-v1"
    input_artifacts = ("meta",)

    def __init__(self) -> None:
        self.calls = 0

    async def detect(self, source_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"ran": self.calls, "has_meta": params["artifacts"]["meta"] is not None}


class SourceLessStubWorker(IntelligenceWorker):
    kind = "source_less"
    version = "source_less-v1"
    needs_source = False

    def __init__(self) -> None:
        self.received_source: Path | None = "sentinel"  # type: ignore[assignment]

    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        self.received_source = source_path
        return {"computed": True}


def _video(video_id: uuid.UUID) -> Video:
    return Video(
        id=video_id,
        project_id=uuid.uuid4(),
        original_filename="clip.mp4",
        storage_key=f"videos/{video_id}/clip.mp4",
        content_type="video/mp4",
        size_bytes=0,
        status="processing",
    )


def _service(
    video_id: uuid.UUID,
    storage: FakeStorage,
    store: FakeArtifactStore,
    repo: FakeArtifactRepo,
) -> IntelligenceService:
    video = _video(video_id)
    storage.objects[video.storage_key] = b"fake video bytes"
    return IntelligenceService(
        videos=FakeVideoRepo(video),
        artifacts=repo,
        store=store,
        storage=storage,
    )


@pytest.mark.asyncio
async def test_process_computes_and_persists() -> None:
    video_id = uuid.uuid4()
    storage = FakeStorage()
    store = FakeArtifactStore()
    repo = FakeArtifactRepo()
    service = _service(video_id, storage, store, repo)
    worker = StubWorker()

    outcome, artifact = await service.process(video_id, worker)

    assert outcome == COMPUTED
    assert artifact is not None
    assert artifact.version == "stub-v1"
    assert worker.calls == 1
    payload = await store.read_payload(video_id, "stub")
    assert payload == {"ran": 1, "has_meta": False}


@pytest.mark.asyncio
async def test_process_caches_when_artifact_is_current() -> None:
    video_id = uuid.uuid4()
    storage = FakeStorage()
    store = FakeArtifactStore()
    repo = FakeArtifactRepo()
    service = _service(video_id, storage, store, repo)
    worker = StubWorker()

    await service.process(video_id, worker)
    outcome, _ = await service.process(video_id, worker)

    assert outcome == CACHED
    assert worker.calls == 1


@pytest.mark.asyncio
async def test_process_recomputes_when_version_changes() -> None:
    video_id = uuid.uuid4()
    storage = FakeStorage()
    store = FakeArtifactStore()
    repo = FakeArtifactRepo()
    service = _service(video_id, storage, store, repo)
    worker = StubWorker()

    await service.process(video_id, worker)
    # bump the worker version -> cache invalidated
    new_worker = StubWorker()
    new_worker.version = "stub-v2"
    outcome, artifact = await service.process(video_id, new_worker)

    assert outcome == COMPUTED
    assert artifact.version == "stub-v2"


@pytest.mark.asyncio
async def test_process_passes_dependency_artifacts() -> None:
    video_id = uuid.uuid4()
    storage = FakeStorage()
    store = FakeArtifactStore()
    repo = FakeArtifactRepo()
    service = _service(video_id, storage, store, repo)
    worker = StubWorker()

    await repo.create(await store.write(video_id, "meta", {"duration_seconds": 12.0}, "meta-v1"))

    await service.process(video_id, worker)
    payload = await store.read_payload(video_id, "stub")
    assert payload["has_meta"] is True


@pytest.mark.asyncio
async def test_process_skips_download_when_worker_does_not_need_source() -> None:
    video_id = uuid.uuid4()
    storage = FakeStorage()  # deliberately empty: no source blob
    store = FakeArtifactStore()
    repo = FakeArtifactRepo()
    video = _video(video_id)
    service = IntelligenceService(
        videos=FakeVideoRepo(video),
        artifacts=repo,
        store=store,
        storage=storage,
    )
    worker = SourceLessStubWorker()

    outcome, _ = await service.process(video_id, worker)

    assert outcome == COMPUTED
    assert worker.received_source is None
    payload = await store.read_payload(video_id, "source_less")
    assert payload == {"computed": True}


@pytest.mark.asyncio
async def test_process_raises_for_missing_video() -> None:
    video_id = uuid.uuid4()
    service = IntelligenceService(
        videos=FakeVideoRepo(None),
        artifacts=FakeArtifactRepo(),
        store=FakeArtifactStore(),
        storage=FakeStorage(),
    )
    with pytest.raises(ValueError, match="video not found"):
        await service.process(video_id, StubWorker())
