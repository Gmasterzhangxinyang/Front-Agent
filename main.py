import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings
from database import init_db
from webhooks.front_webhook import (
    router as webhook_router,
    validate_webhook_security_config,
)
from routes.ops import router as ops_router
from services.ops_auth import validate_ops_auth_config
from tasks.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_webhook_security_config()
    validate_ops_auth_config()
    await init_db()
    try:
        if settings.enable_scheduler:
            start_scheduler()
        yield
    finally:
        if settings.enable_scheduler:
            await stop_scheduler()


app = FastAPI(title="Dify Email Automation", lifespan=lifespan)


@app.middleware("http")
async def add_ops_security_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/ops"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(webhook_router)
app.include_router(ops_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
