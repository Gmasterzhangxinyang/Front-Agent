import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings
from database import init_db
from webhooks.front_webhook import router as webhook_router
from routes.ops import router as ops_router
from tasks.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.enable_scheduler:
        start_scheduler()
    yield


app = FastAPI(title="Dify Email Automation", lifespan=lifespan)
app.include_router(webhook_router)
app.include_router(ops_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
