import logging
import sys
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import init_db
from webhooks.front_webhook import router as webhook_router
from webhooks.feishu_card import router as feishu_card_router
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
app.include_router(feishu_card_router)
app.include_router(feedback_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/feishu/get_chat_id")
async def get_feishu_chat_id(user_open_id: str = ""):
    from tools.feishu import _get_tenant_token
    token = await _get_tenant_token()
    if not token:
        return {"error": "No Feishu app credentials configured"}
    if not user_open_id:
        return {"error": "Pass your open_id as ?user_open_id=ou_xxx. Find it at: https://open.feishu.cn/api-explorer/cli_a96df2401b791cc0?apiName=get&version=v3&resource=bot (call bot/v3/info as user)"}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": user_open_id,
                "msg_type": "text",
                "content": '{"text":"Hello from Bobby的小猫 — setup test"}',
            },
        )
        data = r.json()
        if data.get("code") == 0:
            chat_id = data["data"].get("chat_id", "")
            return {"chat_id": chat_id, "message_id": data["data"].get("message_id"), "hint": f"Set FEISHU_BOT_CHAT_ID={chat_id} in .env"}
        return data
