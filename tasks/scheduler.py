import logging
import asyncio
from functools import wraps
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import AsyncSessionLocal
from models import ConversationState
from sqlalchemy import select
from tools.front import resolve_conversation
from tools.sybil_digest import send_pending_sybil_digest as _send_pending_sybil_digest
import httpx

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
SUPPORT_INBOX_ID = "inb_f9fvf"

from config import settings

_running_scheduler_jobs: set[asyncio.Task] = set()
SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS = 60


def _track_scheduler_job(func):
    @wraps(func)
    async def tracked(*args, **kwargs):
        task = asyncio.current_task()
        if task is not None:
            _running_scheduler_jobs.add(task)
        try:
            return await func(*args, **kwargs)
        finally:
            if task is not None:
                _running_scheduler_jobs.discard(task)

    return tracked


async def _front_get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    last_error = None
    for attempt in range(1, 4):
        try:
            return await client.get(url, **kwargs)
        except httpx.HTTPError as e:
            last_error = e
            logger.warning("Front GET failed (%s/3): %s", attempt, e)
            if attempt < 3:
                await asyncio.sleep(attempt)
    assert last_error is not None
    raise last_error


async def sync_missing_conversations():
    """Scan Front for conversations we haven't processed (no state in DB).

    This catches cases where Front webhook was not received or was dropped.
    Only processes the 50 most recent unassigned conversations in Support.
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
            try:
                r = await _front_get(
                    client,
                    f"https://api2.frontapp.com/inboxes/{SUPPORT_INBOX_ID}/conversations",
                    params={"limit": 50, "status": "unassigned"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as e:
                logger.warning("sync_missing_conversations: Front API request failed: %s", e)
                return
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
                try:
                    r2 = await _front_get(
                        client,
                        f"https://api2.frontapp.com/conversations/{cid}/messages",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except httpx.HTTPError as e:
                    logger.error("sync_missing_conversations: failed to fetch messages for %s: %s", cid, e)
                    continue
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


@_track_scheduler_job
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


@_track_scheduler_job
async def send_pending_sybil_digest():
    return await _send_pending_sybil_digest()


async def refresh_draft_adoption_metrics():
    try:
        from services.draft_adoption import refresh_draft_adoptions

        async with AsyncSessionLocal() as db:
            result = await refresh_draft_adoptions(
                db,
                since=datetime.utcnow() - timedelta(days=30),
                limit=300,
            )
        logger.info("Refreshed draft adoption metrics before ops report: %s", result)
    except Exception:
        logger.exception("refresh_draft_adoption_metrics failed")


@_track_scheduler_job
async def refresh_ops_conversation_metadata():
    try:
        from services.ops_metadata import enrich_missing_conversation_metadata

        async with AsyncSessionLocal() as db:
            result = await asyncio.wait_for(
                enrich_missing_conversation_metadata(db, limit=20),
                timeout=60,
            )
        if result["selected"]:
            logger.info("Refreshed Ops conversation metadata: %s", result)
    except Exception:
        logger.exception("refresh_ops_conversation_metadata failed")


@_track_scheduler_job
async def generate_ops_reports():
    try:
        from routes.ops import generate_all_ops_reports

        await refresh_draft_adoption_metrics()
        await generate_all_ops_reports()
    except Exception:
        logger.exception("generate_ops_reports failed")


@_track_scheduler_job
async def retry_pending_front_webhooks():
    try:
        from webhooks.front_webhook import retry_due_front_webhooks

        result = await retry_due_front_webhooks()
        if result["due"]:
            logger.info("Retried pending Front webhooks: %s", result)
    except Exception:
        logger.exception("retry_pending_front_webhooks failed")


async def stop_scheduler():
    if not scheduler.running:
        return

    scheduler.pause()
    # Let already-submitted coroutine jobs enter their tracked wrappers.
    await asyncio.sleep(0)
    current = asyncio.current_task()
    pending = {
        task
        for task in _running_scheduler_jobs
        if task is not current and not task.done()
    }
    if pending:
        _, unfinished = await asyncio.wait(
            pending,
            timeout=SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS,
        )
        if unfinished:
            logger.warning(
                "Cancelling %s scheduler job(s) after %ss shutdown timeout",
                len(unfinished),
                SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS,
            )

    scheduler.shutdown(wait=False)
    # AsyncIOScheduler schedules its shutdown callback onto this event loop.
    await asyncio.sleep(0)


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
    scheduler.add_job(
        refresh_ops_conversation_metadata,
        "interval",
        minutes=15,
        id="refresh_ops_conversation_metadata_every_15m",
        replace_existing=True,
        next_run_time=datetime.now(),
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        generate_ops_reports,
        "interval",
        hours=3,
        id="generate_ops_reports_every_3h",
        replace_existing=True,
        next_run_time=datetime.now(),
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        retry_pending_front_webhooks,
        "interval",
        minutes=1,
        id="retry_pending_front_webhooks_every_minute",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # sync_missing_conversations disabled - only process webhook-triggered emails
    # scheduler.add_job(sync_missing_conversations, "interval", minutes=10)
    if not scheduler.running:
        scheduler.start()
