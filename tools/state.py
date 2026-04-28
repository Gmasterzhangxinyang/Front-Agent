from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import ConversationState


async def get_state(db: AsyncSession, conversation_id: str) -> ConversationState | None:
    result = await db.execute(select(ConversationState).where(ConversationState.conversation_id == conversation_id))
    return result.scalar_one_or_none()


async def get_user_history(db: AsyncSession, sender_email: str, days: int = 30) -> list[dict]:
    """Get user's conversation history from the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(ConversationState)
        .where(ConversationState.sender_email == sender_email)
        .where(ConversationState.created_at >= cutoff)
        .order_by(ConversationState.created_at.desc())
    )
    states = result.scalars().all()
    return [
        {
            "conversation_id": s.conversation_id,
            "category": s.category,
            "sub_type": s.sub_type,
            "step": s.step,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in states
    ]


async def set_state(
    db: AsyncSession,
    conversation_id: str,
    category: str,
    sub_type: str | None,
    step: str,
    payload: dict,
    waiting: bool = False,
    sender_email: str | None = None,
) -> ConversationState:
    state = await get_state(db, conversation_id)
    if state is None:
        state = ConversationState(conversation_id=conversation_id)
        db.add(state)
    state.category = category
    state.sub_type = sub_type
    state.step = step
    state.payload = payload
    state.waiting_since = datetime.utcnow() if waiting else None
    if sender_email:
        state.sender_email = sender_email
    await db.commit()
    await db.refresh(state)
    return state


async def clear_state(db: AsyncSession, conversation_id: str) -> None:
    state = await get_state(db, conversation_id)
    if state:
        await db.delete(state)
        await db.commit()
