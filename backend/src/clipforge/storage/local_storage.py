import hashlib
import hmac
import shutil
import time
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from clipforge.common.errors import EntityNotFoundError
from clipforge.common.ports import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(
        self,
        root: str,
        signing_secret: str,
        base_url: str,
        url_prefix: str = "/api/v1/storage",
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._secret = signing_secret.encode()
        self._base_url = base_url.rstrip("/")
        self._url_prefix = url_prefix.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError("storage key escapes the configured root")
        return path

    def _sign(self, key: str, expires_at: int) -> str:
        message = f"{key}:{expires_at}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    async def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            shutil.copyfileobj(data, fh)

    async def get(self, key: str) -> BinaryIO:
        path = self._path(key)
        if not path.exists():
            raise EntityNotFoundError(f"object not found: {key}")
        return path.open("rb")

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        expires_at = int(time.time()) + expires_in
        token = self._sign(key, expires_at)
        return (
            f"{self._base_url}{self._url_prefix}/{quote(key)}"
            f"?action=upload&expires={expires_at}&token={token}"
        )

    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        expires_at = int(time.time()) + expires_in
        token = self._sign(key, expires_at)
        return (
            f"{self._base_url}{self._url_prefix}/{quote(key)}"
            f"?action=download&expires={expires_at}&token={token}"
        )
