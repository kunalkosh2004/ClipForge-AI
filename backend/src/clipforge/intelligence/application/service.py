import uuid
from pathlib import Path
from typing import Any

from clipforge.artifacts.domain.entities import Artifact
from clipforge.artifacts.domain.ports import ArtifactRepository, ArtifactStore
from clipforge.common import logging as logging_mod
from clipforge.common.ports import StorageProvider
from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.processing.infrastructure.ffprobe import download_to_tempfile
from clipforge.videos.domain.ports import VideoRepository

logger = logging_mod.get_logger(__name__)

CACHED = "cached"
COMPUTED = "computed"


class IntelligenceService:
    """Runs one intelligence worker for a video.

    Responsibilities: cache check (artifact exists for the same worker
    version), source download, dependency-artifact loading, detector
    execution, validation and artifact persistence. Never touches workflow
    state or events — the tasks layer owns those.
    """

    def __init__(
        self,
        videos: VideoRepository,
        artifacts: ArtifactRepository,
        store: ArtifactStore,
        storage: StorageProvider,
    ) -> None:
        self._videos = videos
        self._artifacts = artifacts
        self._store = store
        self._storage = storage

    async def process(
        self, video_id: uuid.UUID, worker: IntelligenceWorker
    ) -> tuple[str, Artifact | None]:
        """Run `worker` for the video. Returns ("cached"|"computed", artifact).

        Cached means the exact (kind, worker version) artifact already exists
        and its blob is present — nothing was recomputed.
        """
        existing = await self._artifacts.get_latest(video_id, worker.kind)
        if (
            existing is not None
            and existing.version == worker.version
            and await self._store.exists(video_id, worker.kind)
        ):
            logger.info(
                "worker_cached",
                video_id=str(video_id),
                kind=worker.kind,
                version=worker.version,
            )
            return CACHED, existing

        video = await self._videos.get_by_id(video_id)
        if video is None:
            raise ValueError(f"video not found: {video_id}")

        source_path: Path | None = None
        if worker.needs_source:
            source_path, _, _ = await download_to_tempfile(
                self._storage, video.storage_key
            )
        try:
            params = await self._dependency_payloads(video_id, worker.input_artifacts)
            payload = await worker.detect(source_path, params)
            worker.validate(payload)
            artifact = await self._store.write(
                video_id, worker.kind, payload, worker.version
            )
            await self._artifacts.create(artifact)
            return COMPUTED, artifact
        finally:
            if source_path is not None:
                source_path.unlink(missing_ok=True)

    async def _dependency_payloads(
        self, video_id: uuid.UUID, kinds: tuple[str, ...]
    ) -> dict[str, Any]:
        artifacts: dict[str, Any] = {}
        for kind in kinds:
            artifact = await self._artifacts.get_latest(video_id, kind)
            if artifact is None:
                artifacts[kind] = None
                continue
            artifacts[kind] = await self._store.read_payload(video_id, kind)
        return {"artifacts": artifacts}
