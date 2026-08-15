import io
from typing import Any

import pytest
from botocore.exceptions import ClientError

from clipforge.common.errors import EntityNotFoundError
from clipforge.storage.s3_storage import S3StorageProvider, _build_client


class FakeS3Client:
    """Minimal stand-in for a boto3 S3 client (no network, no moto)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_content_types: dict[str, str] = {}
        self.presigned: list[tuple[str, dict[str, Any], int]] = []

    def _not_found(self, key: str) -> ClientError:
        return ClientError(
            {
                "Error": {"Code": "404", "Message": "Not Found"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            },
            "GetObject",
        )

    def upload_fileobj(
        self,
        fileobj: Any,
        bucket: str,
        key: str,
        extra_args: dict[str, Any] | None = None,
    ) -> None:
        assert bucket == "clipforge-test"
        data = fileobj.read()
        self.objects[key] = data
        if extra_args:
            self.put_content_types[key] = extra_args.get("ContentType", "")

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        assert Bucket == "clipforge-test"
        if Key not in self.objects:
            raise self._not_found(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        assert Bucket == "clipforge-test"
        if Key not in self.objects:
            raise self._not_found(Key)
        return {}

    def delete_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        assert Bucket == "clipforge-test"
        self.objects.pop(Key, None)
        return {}

    def generate_presigned_url(
        self,
        client_method: str,
        Params: dict[str, Any] | None = None,
        ExpiresIn: int = 3600,
    ) -> str:
        params = Params or {}
        self.presigned.append((client_method, params, ExpiresIn))
        return (
            f"https://clipforge-test.s3.amazonaws.com/{params['Key']}"
            f"?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires={ExpiresIn}"
        )


@pytest.fixture
def provider() -> tuple[S3StorageProvider, FakeS3Client]:
    client = FakeS3Client()
    provider = S3StorageProvider(bucket="clipforge-test", client=client)
    return provider, client


@pytest.mark.asyncio
async def test_put_get_roundtrip(provider: tuple[S3StorageProvider, FakeS3Client]) -> None:
    storage, client = provider
    await storage.put("videos/abc/clip.mp4", io.BytesIO(b"hello bytes"), "video/mp4")
    assert client.objects["videos/abc/clip.mp4"] == b"hello bytes"
    assert client.put_content_types["videos/abc/clip.mp4"] == "video/mp4"

    handle = await storage.get("videos/abc/clip.mp4")
    with handle:
        assert handle.read() == b"hello bytes"


@pytest.mark.asyncio
async def test_get_chunked_reads(provider: tuple[S3StorageProvider, FakeS3Client]) -> None:
    storage, _ = provider
    await storage.put("big/obj", io.BytesIO(b"0123456789"), "application/octet-stream")
    handle = await storage.get("big/obj")
    with handle:
        assert handle.read(4) == b"0123"
        assert handle.read(4) == b"4567"


@pytest.mark.asyncio
async def test_get_missing_raises_entity_not_found(
    provider: tuple[S3StorageProvider, FakeS3Client],
) -> None:
    storage, _ = provider
    with pytest.raises(EntityNotFoundError):
        await storage.get("missing/obj")


@pytest.mark.asyncio
async def test_exists(provider: tuple[S3StorageProvider, FakeS3Client]) -> None:
    storage, _ = provider
    assert not await storage.exists("missing/obj")
    await storage.put("present/obj", io.BytesIO(b"x"), "text/plain")
    assert await storage.exists("present/obj")


@pytest.mark.asyncio
async def test_delete_removes_object(provider: tuple[S3StorageProvider, FakeS3Client]) -> None:
    storage, _ = provider
    await storage.put("gone/obj", io.BytesIO(b"x"), "text/plain")
    assert await storage.exists("gone/obj")
    await storage.delete("gone/obj")
    assert not await storage.exists("gone/obj")
    # Deleting a missing key is a no-op (S3 semantics).
    await storage.delete("gone/obj")


@pytest.mark.asyncio
async def test_signed_upload_url(provider: tuple[S3StorageProvider, FakeS3Client]) -> None:
    storage, client = provider
    url = await storage.signed_upload_url("videos/abc/clip.mp4", "video/mp4", expires_in=900)
    assert url.startswith("https://clipforge-test.s3.amazonaws.com/videos/abc/clip.mp4?")
    assert "X-Amz-Expires=900" in url
    method, params, expires = client.presigned[-1]
    assert method == "put_object"
    assert params == {
        "Bucket": "clipforge-test",
        "Key": "videos/abc/clip.mp4",
        "ContentType": "video/mp4",
    }
    assert expires == 900


@pytest.mark.asyncio
async def test_signed_download_url(provider: tuple[S3StorageProvider, FakeS3Client]) -> None:
    storage, client = provider
    url = await storage.signed_download_url("clips/abc/out.mp4")
    assert url.startswith("https://clipforge-test.s3.amazonaws.com/clips/abc/out.mp4?")
    method, params, _ = client.presigned[-1]
    assert method == "get_object"
    assert params == {"Bucket": "clipforge-test", "Key": "clips/abc/out.mp4"}


def test_build_client_uses_regional_addressing() -> None:
    """Presigned URLs must target the regional endpoint, not the global one —
    the global endpoint 307-redirects for buckets outside us-east-1, which
    breaks the signature and kills browser uploads/downloads."""
    client = _build_client(
        region="ap-south-1",
        access_key_id="AKIA_TEST",
        secret_access_key="secret",
        endpoint_url=None,
    )
    assert client.meta.region_name == "ap-south-1"
    assert client.meta.config.s3["addressing_style"] == "virtual"
    # No endpoint_url override: the SDK targets the regional endpoint, so
    # presigned URLs use {bucket}.s3.{region}.amazonaws.com (no redirect).
    assert client.meta.endpoint_url == "https://s3.ap-south-1.amazonaws.com"
