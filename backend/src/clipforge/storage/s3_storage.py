"""S3-backed :class:`StorageProvider` (AWS S3 and S3-compatible endpoints).

Swapped in via ``STORAGE_BACKEND=s3``. Uploads and downloads bypass the API
through presigned URLs, so large videos never proxy through the web service;
the worker talks to the bucket directly over the SDK.
"""

import asyncio
from typing import Any, BinaryIO, cast

from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from clipforge.common.errors import EntityNotFoundError
from clipforge.common.ports import StorageProvider


class S3ObjectStream:
    """File-like wrapper around a botocore ``StreamingBody``.

    Supports the two consumption patterns used by the platform:
    ``handle.read(n)`` chunked reads (``download_to_tempfile``) and
    ``with handle:`` context-manager reads (``StorageArtifactStore``).
    """

    def __init__(self, body: Any) -> None:
        self._body = body

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()

    def __enter__(self) -> "S3ObjectStream":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _is_not_found(exc: ClientError) -> bool:
    return exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404


class S3StorageProvider(StorageProvider):
    def __init__(
        self,
        bucket: str,
        *,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
        client: BaseClient | None = None,
    ) -> None:
        """Create a provider for ``bucket``.

        ``client`` is injectable for tests; otherwise a boto3 client is built
        from the AWS credentials (explicit keys, or the ambient environment /
        IAM role) and ``endpoint_url`` (Cloudflare R2, MinIO, LocalStack, ...).
        """
        self._bucket = bucket
        self._client = client or _build_client(
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
        )

    async def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.upload_fileobj,
            data,
            self._bucket,
            key,
            {"ContentType": content_type},
        )

    async def get(self, key: str) -> BinaryIO:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise EntityNotFoundError(f"object not found: {key}") from exc
            raise
        return cast(BinaryIO, S3ObjectStream(response["Body"]))

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise

    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def _build_client(
    *,
    region: str,
    access_key_id: str | None,
    secret_access_key: str | None,
    endpoint_url: str | None,
) -> BaseClient:
    import boto3

    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": region,
        "config": BotoConfig(
            signature_version="s3v4",
            # Virtual-hosted addressing pins presigned URLs to the regional
            # endpoint ({bucket}.s3.{region}.amazonaws.com). With "auto" the
            # global endpoint is used, which 307-redirects for buckets outside
            # us-east-1 — the redirect breaks the signature and browser
            # uploads/downloads fail with 403.
            s3={"addressing_style": "virtual"},
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    }
    if access_key_id and secret_access_key:
        kwargs["aws_access_key_id"] = access_key_id
        kwargs["aws_secret_access_key"] = secret_access_key
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client(**kwargs)
