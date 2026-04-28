import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import AsyncSessionLocal
from models import ConversationState
from sqlalchemy import select
from tools.front import resolve_conversation

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


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
    scheduler.add_job(auto_close_stale_conversations, "interval", hours=6)
    scheduler.start()
