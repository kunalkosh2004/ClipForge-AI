
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis
from sqlalchemy import text

from clipforge.config import get_settings
from clipforge.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "up"
    except Exception:
        checks["database"] = "down"

    try:
        client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        await client.ping()
        await client.aclose()
        checks["redis"] = "up"
    except Exception:
        checks["redis"] = "down"

    healthy = all(status == "up" for status in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
