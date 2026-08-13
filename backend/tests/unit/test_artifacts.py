import hashlib
import io
import uuid
from typing import BinaryIO

import pytest

from clipforge.artifacts.infrastructure.storage_store import StorageArtifactStore
from clipforge.common.ports import StorageProvider


class FakeStorage(StorageProvider):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        self.objects[key] = data.read()

    async def get(self, key: str) -> BinaryIO:
        if key not in self.objects:
            raise FileNotFoundError(key)
        return io.BytesIO(self.objects[key])

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return f"https://upload/{key}"

    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://download/{key}"


@pytest.mark.asyncio
async def test_write_then_read_roundtrip() -> None:
    storage = FakeStorage()
    store = StorageArtifactStore(storage)
    video_id = uuid.uuid4()

    artifact = await store.write(video_id, "scene", {"scenes": [{"start_time": 0.0}]}, "scene-v1")

    assert artifact.kind == "scene"
    assert artifact.version == "scene-v1"
    assert artifact.storage_key == f"artifacts/{video_id}/scene.json"
    assert await store.exists(video_id, "scene")
    payload = await store.read_payload(video_id, "scene")
    assert payload == {"scenes": [{"start_time": 0.0}]}


@pytest.mark.asyncio
async def test_checksum_matches_written_blob() -> None:
    storage = FakeStorage()
    store = StorageArtifactStore(storage)
    video_id = uuid.uuid4()

    artifact = await store.write(video_id, "beat", {"peaks": [1.0, 2.0]}, "beat-v1")
    raw = storage.objects[artifact.storage_key]
    assert artifact.checksum == hashlib.sha256(raw).hexdigest()
    assert artifact.size_bytes == len(raw)


@pytest.mark.asyncio
async def test_read_missing_returns_none() -> None:
    store = StorageArtifactStore(FakeStorage())
    assert await store.read_payload(uuid.uuid4(), "nope") is None
    assert not await store.exists(uuid.uuid4(), "nope")


@pytest.mark.asyncio
async def test_document_envelope_is_self_describing() -> None:
    storage = FakeStorage()
    store = StorageArtifactStore(storage)
    video_id = uuid.uuid4()
    await store.write(video_id, "motion", {"has_motion": True}, "motion-v1")

    raw = storage.objects[f"artifacts/{video_id}/motion.json"]
    import json

    doc = json.loads(raw.decode("utf-8"))
    assert doc["schema_version"] == 1
    assert doc["kind"] == "motion"
    assert doc["version"] == "motion-v1"
    assert doc["video_id"] == str(video_id)
    assert doc["payload"] == {"has_motion": True}
