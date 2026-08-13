import hashlib
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from clipforge.artifacts.domain.entities import Artifact
from clipforge.artifacts.domain.ports import ArtifactStore
from clipforge.common.ports import StorageProvider

ARTIFACT_SCHEMA_VERSION = 1


class StorageArtifactStore(ArtifactStore):
    """ArtifactStore backed by the platform's StorageProvider.

    Documents are written to `artifacts/{video_id}/{kind}.json` and wrapped in
    a stable envelope (`schema_version`, `kind`, `version`, `created_at`,
    `payload`) so downstream consumers never depend on a worker's internal
    shape and the blob is self-describing.
    """

    def __init__(self, storage: StorageProvider) -> None:
        self._storage = storage

    @staticmethod
    def _key(video_id: uuid.UUID, kind: str) -> str:
        return f"artifacts/{video_id}/{kind}.json"

    @staticmethod
    def _document(
        video_id: uuid.UUID,
        kind: str,
        version: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "kind": kind,
            "version": version,
            "video_id": str(video_id),
            "created_at": created_at,
            "payload": payload,
        }

    async def write(
        self,
        video_id: uuid.UUID,
        kind: str,
        payload: dict[str, Any],
        version: str,
    ) -> Artifact:
        created_at = datetime.now(UTC).isoformat()
        document = self._document(video_id, kind, version, payload, created_at)
        raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
        key = self._key(video_id, kind)
        await self._storage.put(key, io.BytesIO(raw), "application/json")
        return Artifact(
            video_id=video_id,
            kind=kind,
            version=version,
            storage_key=key,
            checksum=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )

    async def read_payload(self, video_id: uuid.UUID, kind: str) -> dict[str, Any] | None:
        try:
            handle = await self._storage.get(self._key(video_id, kind))
        except FileNotFoundError:
            return None
        with handle:
            document: dict[str, Any] = json.loads(handle.read().decode("utf-8"))
        return cast(dict[str, Any] | None, document.get("payload"))

    async def exists(self, video_id: uuid.UUID, kind: str) -> bool:
        return await self._storage.exists(self._key(video_id, kind))
