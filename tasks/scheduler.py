import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import AsyncSessionLocal
from models import ConversationState
from sqlalchemy import select
from tools.front import resolve_conversation
from tools.sybil_digest import send_pending_sybil_digest
import httpx

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

from config import settings


async def sync_missing_conversations():
    """Scan Front for conversations we haven't processed (no state in DB).

    This catches cases where Front webhook was not received or was dropped.
    Only processes the 50 most recent unassigned conversations.
    Skips archived conversations and those already in our state DB.
    """
    token = settings.front_api_token
    if not token:
        logger.warning("sync_missing_conversations: no Front token")
        return

    async with AsyncSessionLocal() as db:
        # Get known conversation IDs
        result = await db.execute(select(ConversationState.conversation_id))
        known = {row[0] for row in result.fetchall()}

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                "https://api2.frontapp.com/conversations",
                params={"limit": 50, "status": "unassigned"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code != 200:
                logger.warning(f"sync_missing_conversations: Front API {r.status_code}")
                return

            conversations = r.json().get("_results", [])
            processed = 0

            for conv in conversations:
                cid = conv["id"]
                if cid in known:
                    continue

                # Skip if already archived
                if conv.get("status") == "archived":
                    continue

                # Fetch the latest message to get sender info
                r2 = await client.get(
                    f"https://api2.frontapp.com/conversations/{cid}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if r2.status_code != 200:
                    continue

                messages = r2.json().get("_results", [])
                if not messages:
                    continue

                latest = messages[0]

                # Skip outbound-only messages (no inbound from customer)
                if not latest.get("is_inbound"):
                    continue

                sender = latest.get("sender", {})
                sender_email = sender.get("handle", "")
                message_body = latest.get("text") or latest.get("body") or ""
                attachments = latest.get("attachments") or []

                logger.info(f"sync_missing_conversations: processing {cid}")
                try:
                    from agent.orchestrator import handle_email

                    await handle_email(
                        conversation_id=cid,
                        message_body=message_body,
                        sender_email=sender_email,
                        attachments=attachments,
                        db=db,
                    )
                    await db.commit()
                    processed += 1
                except Exception as e:
                    logger.error(f"sync_missing_conversations: error on {cid}: {e}")

            if processed:
                logger.info(f"sync_missing_conversations: processed {processed} conversations")


async def auto_close_stale_conversations():
    cutoff = datetime.utcnow() - timedelta(days=10)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationState).where(
                ConversationState.waiting_since != None,
                ConversationState.waiting_since < cutoff,
                ConversationState.step != "done",
            )
        )
        stale = result.scalars().all()
        for state in stale:
            logger.info(f"Auto-closing stale conversation {state.conversation_id}")
            await resolve_conversation(state.conversation_id)
            state.step = "done"
            state.waiting_since = None
        await db.commit()


def start_scheduler():
    scheduler.add_job(
        auto_close_stale_conversations,
        "interval",
        hours=6,
        id="auto_close_stale_conversations",
        replace_existing=True,
    )
    scheduler.add_job(
        send_pending_sybil_digest,
        "cron",
        hour=10,
        minute=0,
        timezone="Asia/Shanghai",
        id="send_pending_sybil_digest_cn_10am",
        replace_existing=True,
    )
    # sync_missing_conversations disabled - only process webhook-triggered emails
    # scheduler.add_job(sync_missing_conversations, "interval", minutes=10)
    if not scheduler.running:
        scheduler.start()
