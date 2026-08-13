import hashlib
import hmac
import io
import time

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from clipforge.api.deps import get_container
from clipforge.common.errors import AuthenticationError, EntityNotFoundError, UserError

router = APIRouter(prefix="/storage", tags=["storage"])

MAX_UPLOAD_BYTES = 1_073_741_824  # 1 GiB dev ceiling; S3-style multipart later


def _verify_signature(secret: str, key: str, action: str, expires: str, token: str) -> None:
    try:
        expires_at = int(expires)
    except ValueError:
        raise AuthenticationError("invalid expiry") from None
    if expires_at < int(time.time()):
        raise AuthenticationError("signed URL expired")
    expected = hmac.new(
        secret.encode(), f"{key}:{expires_at}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, token):
        raise AuthenticationError("invalid signature")


@router.put("/{key:path}")
async def upload_object(
    key: str,
    request: Request,
    action: str = Query(...),
    expires: str = Query(...),
    token: str = Query(...),
) -> JSONResponse:
    container = get_container(request)
    secret = container.settings.storage_signing_secret.get_secret_value()
    _verify_signature(secret, key, action, expires, token)
    if action != "upload":
        raise UserError("invalid action for this endpoint")

    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_UPLOAD_BYTES:
        raise UserError("upload exceeds the allowed size")

    body = await request.body()
    if len(body) > MAX_UPLOAD_BYTES:
        raise UserError("upload exceeds the allowed size")

    content_type = request.headers.get("content-type", "application/octet-stream")
    await container.storage.put(key, io.BytesIO(body), content_type)
    return JSONResponse({"ok": True}, status_code=status.HTTP_200_OK)


@router.get("/{key:path}")
async def download_object(
    key: str,
    request: Request,
    action: str = Query(...),
    expires: str = Query(...),
    token: str = Query(...),
) -> StreamingResponse:
    container = get_container(request)
    secret = container.settings.storage_signing_secret.get_secret_value()
    _verify_signature(secret, key, action, expires, token)
    if action != "download":
        raise UserError("invalid action for this endpoint")

    try:
        blob = await container.storage.get(key)
    except EntityNotFoundError:
        raise UserError("object not found") from None
    return StreamingResponse(blob, media_type="application/octet-stream")
