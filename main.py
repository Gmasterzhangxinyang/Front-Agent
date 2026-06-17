import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import init_db
from webhooks.front_webhook import router as webhook_router
from routes.feedback_api import router as feedback_api_router
from routes.feedback import router as feedback_router
from tasks.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield


app = FastAPI(title="Dify Email Automation", lifespan=lifespan)
app.include_router(webhook_router)
app.include_router(feedback_api_router)
app.include_router(feedback_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
