"""FastAPI composition, structured request logs and resource boundaries."""

import asyncio
import contextlib
import json
import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth_routes import router as auth_router
from app.commerce_routes import router as commerce_router
from app.config import get_settings
from app.database import engine
from app.operations_routes import router as operations_router
from app.webhook_routes import router as webhook_router
from app.worker import worker_loop

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("shop.http")
limits = OrderedDict()


@asynccontextmanager
async def lifespan(application):
    """Run a single bounded worker; schema creation belongs to Alembic."""
    task = asyncio.create_task(worker_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Agentic Shop API", version="1.0.0", lifespan=lifespan)
for router in (
    auth_router,
    commerce_router,
    operations_router,
    webhook_router,
):
    app.include_router(router)
Path(get_settings().upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=get_settings().upload_dir))


def rate_limited(request: Request) -> bool:
    """Bound per-host request windows and limiter memory in one worker."""
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    count, reset = limits.pop(key, (0, now + 60))
    if reset <= now:
        count, reset = 0, now + 60
    limits[key] = (count + 1, reset)
    while len(limits) > 2048:
        limits.popitem(last=False)
    return count >= 180


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    """Apply request caps and emit non-secret structured timings."""
    started = time.monotonic()
    length = request.headers.get("content-length", "0")
    if not length.isdigit() or int(length) > 6 * 1024 * 1024:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    if rate_limited(request):
        return JSONResponse(
            {"detail": "Rate limit exceeded"},
            status_code=429,
            headers={"Retry-After": "60"},
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )
    )
    return response


