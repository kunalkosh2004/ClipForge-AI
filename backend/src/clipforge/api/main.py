import asyncio
import contextlib
import uuid

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from clipforge import __version__
from clipforge.admin.api.routes import router as admin_router
from clipforge.analysis.api.routes import router as analysis_router
from clipforge.api.middleware.metrics import PrometheusMiddleware
from clipforge.api.middleware.rate_limit import RateLimitMiddleware
from clipforge.api.routes import health, status, storage
from clipforge.clips.api.routes import router as clips_router
from clipforge.common import logging as logging_mod
from clipforge.common.errors import ClipForgeError
from clipforge.common.observability import (
    render_metrics,
    set_queue_depth,
    setup_metrics,
    setup_tracing,
    trace_id_from_context,
)
from clipforge.config import get_settings
from clipforge.container import Container, build_container
from clipforge.identity.api.routes import router as auth_router
from clipforge.timeline.api.routes import router as timeline_router
from clipforge.usage.api.routes import router as usage_router
from clipforge.videos.api.routes import router as videos_router

logger = logging_mod.get_logger(__name__)

_api_tracer = None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ClipForgeError)
    async def handle_clipforge_error(request: Request, exc: ClipForgeError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "request_error",
            code=exc.code,
            message=exc.message,
            kind=exc.kind.value,
            http_status=exc.http_status,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id,
                }
            },
        )


async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    path = request.url.path
    if _api_tracer is not None:
        with _api_tracer.start_as_current_span(f"{request.method} {path}") as span:
            span.set_attribute("http.request_id", request_id)
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", path)
            with logging_mod.request_context(
                request_id=request_id,
                trace_id=trace_id_from_context() or "none",
                method=request.method,
                path=path,
            ):
                response = await call_next(request)
    else:
        with logging_mod.request_context(
            request_id=request_id,
            trace_id="none",
            method=request.method,
            path=path,
        ):
            response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


async def _poll_queue_depths(settings) -> None:  # type: ignore[no-untyped-def]
    queues = [
        settings.queue_default,
        settings.queue_import,
        settings.queue_ai,
        settings.queue_render,
        settings.queue_dead,
    ]
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            for queue in queues:
                try:
                    depth = await client.llen(f"dramatiq:{queue}")
                    set_queue_depth(queue, int(depth))
                except Exception:
                    logger.warning("queue_depth_poll_failed", queue=queue)
            await asyncio.sleep(5)
    finally:
        await client.aclose()


async def _lifespan(app: FastAPI):
    settings = get_settings()
    poller = asyncio.create_task(_poll_queue_depths(settings))
    try:
        yield
    finally:
        poller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poller


def create_app(container: Container | None = None) -> FastAPI:
    global _api_tracer
    settings = get_settings()
    logging_mod.configure_logging(settings.app_env, settings.log_level)
    setup_metrics()
    _api_tracer = setup_tracing(settings.otel_service_name, settings.otel_enabled)
    container = container or build_container(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=_lifespan,
    )
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.redis_url,
    )
    app.add_middleware(PrometheusMiddleware)
    app.middleware("http")(request_id_middleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(status.router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(usage_router, prefix="/api/v1")
    app.include_router(videos_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    app.include_router(clips_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(storage.router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    return app


app = create_app()
