from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from agent.message_identity import is_internal_email
from models import ConversationAction, ConversationState


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
    # Preserve the original external customer once known. Older records may
    # contain an internal teammate because Front reports internal forwards as
    # inbound; a later real customer message is allowed to repair that value.
    candidate_sender = (sender_email or "").strip()
    if (
        candidate_sender
        and not is_internal_email(candidate_sender)
        and (not state.sender_email or is_internal_email(state.sender_email))
    ):
        state.sender_email = candidate_sender
    await db.commit()
    await db.refresh(state)
    return state


async def clear_state(db: AsyncSession, conversation_id: str) -> None:
    state = await get_state(db, conversation_id)
    if state:
        await db.delete(state)
        await db.commit()

async def get_action(
    db: AsyncSession,
    conversation_id: str,
    action_type: str,
    action_key: str,
) -> ConversationAction | None:
    result = await db.execute(
        select(ConversationAction).where(
            ConversationAction.conversation_id == conversation_id,
            ConversationAction.action_type == action_type,
            ConversationAction.action_key == action_key,
        )
    )
    return result.scalar_one_or_none()


async def get_recent_action_by_type_key(
    db: AsyncSession,
    action_type: str,
    action_key: str,
    *,
    hours: int,
) -> ConversationAction | None:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(ConversationAction)
        .where(
            ConversationAction.action_type == action_type,
            ConversationAction.action_key == action_key,
            ConversationAction.created_at >= cutoff,
        )
        .order_by(ConversationAction.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def record_action(
    db: AsyncSession,
    conversation_id: str,
    action_type: str,
    action_key: str,
    result: str,
) -> ConversationAction:
    existing = await get_action(db, conversation_id, action_type, action_key)
    if existing:
        return existing

    action = ConversationAction(
        conversation_id=conversation_id,
        action_type=action_type,
        action_key=action_key,
        result=result,
    )
    db.add(action)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await get_action(db, conversation_id, action_type, action_key)
        if existing:
            return existing
        raise
    await db.refresh(action)
    return action

