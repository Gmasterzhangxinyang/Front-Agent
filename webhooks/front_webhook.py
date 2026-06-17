import hashlib
import hmac
import json
import logging
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from database import AsyncSessionLocal
from models import WebhookEvent
from agent.orchestrator import handle_email
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.front_webhook_secret:
        return True  # skip verification if secret not configured
    expected = hmac.new(settings.front_webhook_secret.encode(), body, hashlib.sha1)
    import base64
    expected_b64 = base64.b64encode(expected.digest()).decode()
    return hmac.compare_digest(expected_b64, signature)


ALLOWED_INBOX_IDS = {"inb_f9fvf"}  # Support only


@router.post("/webhook/front")
async def front_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Front-Signature", "")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_id = payload.get("id") or payload.get("event_id")
    conversation = payload.get("conversation") or {}
    conversation_id = conversation.get("id") or payload.get("conversation_id")

    if not conversation_id:
        return {"status": "ignored", "reason": "no conversation_id"}

    # Idempotency check
    async with AsyncSessionLocal() as db:
        if event_id:
            existing = await db.execute(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
            if existing.scalar_one_or_none():
                return {"status": "already_processed"}
            db.add(WebhookEvent(event_id=event_id))
            await db.commit()

        # Extract message data
        message = payload.get("target", {}).get("data", {}) or {}
        message_body = message.get("text") or message.get("body") or ""
        sender = message.get("from") or {}
        sender_email = sender.get("handle") or sender.get("email") or ""
        attachments = message.get("attachments") or []

        # Check which inboxes this conversation is in - must be in Support/Hello inboxes
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            ri = await client.get(f"https://api2.frontapp.com/conversations/{conversation_id}/inboxes",
                                  headers={"Authorization": f"Bearer {settings.front_api_token}"})
            if ri.status_code == 200:
                inbox_ids = [i.get("id") for i in ri.json().get("_results", [])]
                if not any(iid in ALLOWED_INBOX_IDS for iid in inbox_ids):
                    logger.info(f"Ignoring conversation {conversation_id} - not in Support/Hello inboxes (inboxes: {inbox_ids})")
                    return {"status": "ignored", "reason": f"conversation not in allowed inbox"}
            else:
                logger.warning(f"Could not check inboxes for {conversation_id}, proceeding anyway")

        try:
            await handle_email(
                conversation_id=conversation_id,
                message_body=message_body,
                sender_email=sender_email,
                attachments=attachments,
                db=db,
            )
        except Exception as e:
            logger.error(f"Error handling email {conversation_id}: {e}", exc_info=True)
            # Notify Bobby on unexpected errors
            from tools.feishu import notify_bobby
            await notify_bobby(f"❌ 邮件处理出错！对话ID: {conversation_id}, 错误: {str(e)[:200]}", conversation_id=conversation_id)

    return {"status": "ok"}
