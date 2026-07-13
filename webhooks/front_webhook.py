import hashlib
import hmac
import json
import logging
import asyncio
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from database import AsyncSessionLocal
from models import WebhookEvent
from agent.orchestrator import handle_email
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_CONCURRENT_WEBHOOKS = 2
_webhook_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WEBHOOKS)
_conversation_locks: dict[str, asyncio.Lock] = {}


def validate_webhook_security_config() -> None:
    if settings.front_webhook_secret:
        return
    if settings.allow_unsigned_front_webhooks:
        logger.warning(
            "Front webhook signature verification is explicitly disabled"
        )
        return
    raise RuntimeError(
        "FRONT_WEBHOOK_SECRET is required unless "
        "ALLOW_UNSIGNED_FRONT_WEBHOOKS=true"
    )


def _get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    lock = _conversation_locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _conversation_locks[conversation_id] = lock
    return lock



def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.front_webhook_secret:
        return settings.allow_unsigned_front_webhooks
    expected = hmac.new(settings.front_webhook_secret.encode(), body, hashlib.sha1)
    import base64
    expected_b64 = base64.b64encode(expected.digest()).decode()
    return hmac.compare_digest(expected_b64, signature)


ALLOWED_INBOX_IDS = {"inb_f9fvf"}  # Support only


def _is_processable_inbound_message(message: dict) -> bool:
    if not message:
        return False
    if message.get("is_draft") is True:
        return False
    if message.get("type") == "comment":
        return False
    if message.get("is_inbound") is False:
        return False
    return bool(message.get("text") or message.get("body") or message.get("attachments"))


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

    async with _webhook_semaphore:
        lock = _get_conversation_lock(conversation_id)
        async with lock:
            return await _process_front_webhook_event(payload, event_id, conversation_id)


async def _process_front_webhook_event(payload: dict, event_id: str | None, conversation_id: str):
    # Idempotency check
    async with AsyncSessionLocal() as db:
        if event_id:
            existing = await db.execute(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
            if existing.scalar_one_or_none():
                return {"status": "already_processed"}

        # Extract message data
        message = payload.get("target", {}).get("data", {}) or {}
        if not _is_processable_inbound_message(message):
            logger.info("Ignoring non-inbound Front event for conversation %s", conversation_id)
            if event_id:
                db.add(WebhookEvent(event_id=event_id))
                await db.commit()
            return {"status": "ignored", "reason": "not inbound user message"}

        message_body = message.get("text") or message.get("body") or ""
        sender = message.get("from") or {}
        sender_email = sender.get("handle") or sender.get("email") or ""
        attachments = message.get("attachments") or []

        # Check which inboxes this conversation is in - must be in Support/Hello inboxes
        from tools import front

        try:
            ri = await front.front_request("GET", f"{front.BASE_URL}/conversations/{conversation_id}/inboxes")
        except Exception as e:
            logger.warning("Could not check inboxes for %s after retries: %r", conversation_id, e)
            raise HTTPException(status_code=503, detail="Front inbox check failed")

        if ri.status_code == 200:
            inbox_ids = [i.get("id") for i in ri.json().get("_results", [])]
            if not any(iid in ALLOWED_INBOX_IDS for iid in inbox_ids):
                logger.info(f"Ignoring conversation {conversation_id} - not in Support/Hello inboxes (inboxes: {inbox_ids})")
                if event_id:
                    db.add(WebhookEvent(event_id=event_id))
                    await db.commit()
                return {"status": "ignored", "reason": f"conversation not in allowed inbox"}
        elif ri.status_code in front.FRONT_TRANSIENT_STATUSES:
            logger.warning("Could not check inboxes for %s, Front returned %s", conversation_id, ri.status_code)
            raise HTTPException(status_code=503, detail="Front inbox check transient failure")
        else:
            logger.warning("Could not check inboxes for %s, Front returned %s; proceeding anyway", conversation_id, ri.status_code)

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
            # Forward unexpected processing errors to Bobby, but keep the
            # original conversation open for manual review. Some Front setups
            # auto-archive after an outgoing message, so explicitly reopen it.
            error_summary = f"❌ 邮件处理出错！对话ID: {conversation_id}, 错误: {str(e)[:200]}"

            try:
                from agent.tool_registry import execute_tool_call

                notify_result = await execute_tool_call(
                    "front_forward_to_bobby",
                    {
                        "message": error_summary,
                        "conversation_id": conversation_id,
                    },
                    db,
                )
                if "failed" in notify_result:
                    logger.warning(
                        "Failed to forward handler error for %s: %s",
                        conversation_id,
                        notify_result,
                    )
            except Exception as notify_error:
                logger.warning("Failed to forward handler error for %s: %s", conversation_id, notify_error)

            try:
                from tools import front

                reopened = await front.reopen_conversation(conversation_id)
                if not reopened:
                    logger.warning("Failed to reopen errored conversation %s", conversation_id)
            except Exception as reopen_error:
                logger.warning("Failed to reopen errored conversation %s: %s", conversation_id, reopen_error)

            try:
                from tools import state as state_tool

                await state_tool.set_state(
                    db,
                    conversation_id,
                    "unclear",
                    None,
                    "failed_needs_review",
                    {"reason": "handler_error", "error": str(e)[:500]},
                    waiting=False,
                    sender_email=sender_email,
                )
            except Exception as state_error:
                logger.warning("Failed to save handler error state for %s: %s", conversation_id, state_error)

            # Do not acknowledge or record a failed event as successfully
            # processed. A retrying proxy or manual redelivery can replay it.
            raise HTTPException(status_code=503, detail="handler_error") from e

        if event_id:
            db.add(WebhookEvent(event_id=event_id))
            await db.commit()

    return {"status": "ok"}
