import time
from collections.abc import Callable

import redis.asyncio as aioredis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from clipforge.common import logging as logging_mod

logger = logging_mod.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        redis_url: str,
        default_limit: int = 60,
        default_window: int = 60,
    ) -> None:
        super().__init__(app)
        self._redis_url = redis_url
        self._default_limit = default_limit
        self._default_window = default_window
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, max_connections=5
            )
        return self._redis

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        path = request.url.path

        if path.startswith("/health") or path.endswith("/docs") or path.endswith("/openapi.json"):
            return await call_next(request)

        ip = self._client_ip(request)
        window = self._default_window
        limit = self._resolve_limit(path, request.method)
        bucket = f"rl:{ip}:{path}"

        try:
            redis = await self._get_redis()
            now = time.time()
            pipe = redis.pipeline()
            pipe.zremrangebyscore(bucket, 0, now - window)
            pipe.zadd(bucket, {f"{now}:{id(request)}": now})
            pipe.zcard(bucket)
            pipe.expire(bucket, window)
            results = await pipe.execute()

            count = results[2]

            if count > limit:
                oldest = await redis.zrange(bucket, 0, 0, withscores=True)
                retry_after = int(window - (now - oldest[0][1])) + 1 if oldest else window
                logger.warning(
                    "rate_limited",
                    ip=ip,
                    path=path,
                    count=count,
                    limit=limit,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": f"Too many requests. Retry after {retry_after}s.",
                        }
                    },
                    headers={"Retry-After": str(max(retry_after, 1))},
                )
        except Exception:
            logger.warning("rate_limit_check_failed; allowing request")

        return await call_next(request)

    def _resolve_limit(self, path: str, method: str) -> int:
        if path.startswith("/api/v1/auth"):
            return 20
        if method == "POST" and path.startswith("/api/v1/videos"):
            return 10
        return self._default_limit
