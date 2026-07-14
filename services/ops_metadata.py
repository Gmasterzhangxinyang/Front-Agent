import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationState
from tools.front import get_conversation

logger = logging.getLogger(__name__)

ATTENTION_STEPS = ("failed_needs_review", "manual_review")
METADATA_CHECKED_AT_KEY = "_ops_metadata_checked_at"


def _clean(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].strip()


def extract_front_metadata(conversation: dict[str, Any]) -> tuple[str, str]:
    recipient = conversation.get("recipient") or {}
    sender = ""
    if isinstance(recipient, dict):
        sender = recipient.get("handle") or recipient.get("email") or ""
    summary = conversation.get("subject") or ""
    return _clean(sender, 320), _clean(summary, 500)


def _missing_metadata_filter():
    displayed_summary = func.coalesce(
        func.nullif(
            func.json_extract(ConversationState.payload, "$.summary"),
            "",
        ),
        func.nullif(
            func.json_extract(ConversationState.payload, "$.reason"),
            "",
        ),
        func.nullif(
            func.json_extract(ConversationState.payload, "$.route"),
            "",
        ),
        "",
    )
    return or_(
        ConversationState.sender_email.is_(None),
        ConversationState.sender_email == "",
        displayed_summary == "",
    )


def _attention_filter():
    return or_(
        ConversationState.step.in_(ATTENTION_STEPS),
        ConversationState.step.like("awaiting%"),
        ConversationState.waiting_since.is_not(None),
    )


async def enrich_missing_conversation_metadata(
    db: AsyncSession,
    *,
    limit: int = 20,
) -> dict[str, int]:
    priority = case((_attention_filter(), 0), else_=1)
    last_checked = func.coalesce(
        func.json_extract(
            ConversationState.payload,
            f"$.{METADATA_CHECKED_AT_KEY}",
        ),
        "",
    )
    result = await db.execute(
        select(ConversationState)
        .where(_missing_metadata_filter())
        .order_by(priority, last_checked, ConversationState.updated_at.desc())
        .limit(limit)
    )
    states = list(result.scalars().all())
    # Close the read transaction before network I/O.
    await db.commit()

    updated = 0
    unchanged = 0
    failed = 0
    for state in states:
        original_updated_at = state.updated_at
        payload = dict(state.payload or {})
        payload[METADATA_CHECKED_AT_KEY] = datetime.now(timezone.utc).isoformat()
        try:
            conversation = await get_conversation(state.conversation_id)
            sender, summary = extract_front_metadata(conversation)
        except Exception as exc:
            failed += 1
            logger.warning(
                "Ops metadata enrichment failed for %s: %s",
                state.conversation_id,
                exc,
            )
            await db.execute(
                update(ConversationState)
                .where(
                    ConversationState.conversation_id
                    == state.conversation_id
                )
                .values(
                    payload=payload,
                    updated_at=original_updated_at,
                )
            )
            await db.commit()
            continue

        changed = False
        stored_sender = state.sender_email
        if not stored_sender and sender:
            stored_sender = sender
            changed = True

        if not payload.get("summary") and summary:
            payload["summary"] = summary
            changed = True

        # Explicitly retain the business timestamp so metadata maintenance does
        # not look like new customer activity in Ops workload metrics.
        await db.execute(
            update(ConversationState)
            .where(
                ConversationState.conversation_id == state.conversation_id
            )
            .values(
                sender_email=stored_sender,
                payload=payload,
                updated_at=original_updated_at,
            )
        )
        await db.commit()
        if changed:
            updated += 1
        else:
            unchanged += 1

    return {
        "selected": len(states),
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
    }
