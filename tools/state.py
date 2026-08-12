from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from agent.message_identity import is_internal_email
from models import ConversationAction, ConversationState


async def get_state(db: AsyncSession, conversation_id: str) -> ConversationState | None:
    result = await db.execute(select(ConversationState).where(ConversationState.conversation_id == conversation_id))
    return result.scalar_one_or_none()


async def get_user_history(
    db: AsyncSession,
    sender_email: str,
    days: int = 30,
    *,
    exclude_conversation_id: str = "",
    limit: int = 5,
) -> list[dict]:
    """Get the same external sender's recent states for cross-thread context."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    normalized_sender = (sender_email or "").strip().lower()
    if not normalized_sender:
        return []

    statement = (
        select(ConversationState)
        .where(func.lower(func.trim(ConversationState.sender_email)) == normalized_sender)
        .where(ConversationState.created_at >= cutoff)
        .order_by(ConversationState.created_at.desc())
        .limit(max(1, min(limit, 10)))
    )
    if exclude_conversation_id:
        statement = statement.where(
            ConversationState.conversation_id != exclude_conversation_id
        )

    result = await db.execute(statement)
    states = result.scalars().all()
    return [
        {
            "conversation_id": state.conversation_id,
            "category": state.category,
            "sub_type": state.sub_type,
            "step": state.step,
            "payload": dict(state.payload or {}),
            "created_at": state.created_at.isoformat() if state.created_at else None,
        }
        for state in states
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

