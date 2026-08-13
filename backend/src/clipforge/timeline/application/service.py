import uuid
from typing import Any

from clipforge.artifacts.domain.ports import ArtifactRepository, ArtifactStore
from clipforge.common.errors import EntityNotFoundError


class TimelineService:
    """Read access to the computed timeline artifact.

    The artifact is produced by the `timeline` workflow node; this service
    only resolves and returns it. Ownership is enforced by the caller via
    `require_owned_video`.
    """

    def __init__(self, artifacts: ArtifactRepository, store: ArtifactStore) -> None:
        self._artifacts = artifacts
        self._store = store

    async def get_timeline(self, video_id: uuid.UUID) -> dict[str, Any]:
        artifact = await self._artifacts.get_latest(video_id, "timeline")
        if artifact is None:
            raise EntityNotFoundError("timeline not computed for this video")
        payload = await self._store.read_payload(video_id, "timeline")
        if payload is None:
            raise EntityNotFoundError("timeline not computed for this video")
        return payload
