import re
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from clipforge.common.observability import record_http_request

_UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_STREAM_ID_PATTERN = re.compile(r"\d{4,}-\d+")


def normalize_path(path: str) -> str:
    path = _UUID_PATTERN.sub("{id}", path)
    path = _STREAM_ID_PATTERN.sub("{id}", path)
    return path


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Any:
        path = normalize_path(request.url.path)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            record_http_request(request.method, path, 500, time.perf_counter() - start)
            raise
        record_http_request(request.method, path, response.status_code, time.perf_counter() - start)
        return response
