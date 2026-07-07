import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationAction, DraftAdoption
from tools.front import get_conversation_messages

DRAFT_TOOL_NAME = "front_create_draft"
STATUS_EXACT_ADOPTED = "exact_adopted"
STATUS_MODIFIED_OR_MANUAL = "modified_or_manual"
STATUS_NOT_SENT = "not_sent"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_UNKNOWN = "unknown"
TERMINAL_STATUSES = {STATUS_EXACT_ADOPTED, STATUS_MODIFIED_OR_MANUAL, STATUS_NOT_SENT}
PENDING_AFTER_HOURS = 24
# Start measuring draft adoption from the rollout point; older drafts were not tracked consistently.
TRACKING_START_AT = datetime(2026, 7, 7, 9, 49, 38)


def effective_since(since: datetime) -> datetime:
    return max(since, TRACKING_START_AT)


@dataclass(frozen=True)
class DraftAdoptionResult:
    status: str
    sent_at: datetime | None = None
    error: str = ""


def normalize_text(value: str | None) -> str:
    text = str(value or "").strip()
    if "<" in text and ">" in text:
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\s*>", "\n\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
    return " ".join(text.split())


def text_hash(value: str | None) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()[:16]


def draft_hash_from_action_key(action_key: str | None) -> str:
    prefix = "body:"
    if not action_key or not action_key.startswith(prefix):
        return ""
    return action_key[len(prefix):].strip()


def parse_front_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.utcfromtimestamp(int(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def is_outbound_sent_message(message: dict[str, Any]) -> bool:
    if message.get("is_draft") is True:
        return False
    if message.get("type") == "comment":
        return False
    if message.get("is_inbound") is True:
        return False
    if message.get("is_inbound") is False:
        return True
    return message.get("type") == "email" and not message.get("is_draft")


def message_body(message: dict[str, Any]) -> str:
    return normalize_text(message.get("text") or message.get("body") or "")


def classify_draft_adoption(
    draft_hash: str,
    draft_created_at: datetime,
    messages: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    pending_after_hours: int = PENDING_AFTER_HOURS,
) -> DraftAdoptionResult:
    if not draft_hash:
        return DraftAdoptionResult(STATUS_UNKNOWN, error="missing_draft_hash")

    now = now or datetime.utcnow()
    outbound_after_draft: list[tuple[datetime, str]] = []
    for message in messages:
        if not is_outbound_sent_message(message):
            continue
        sent_at = parse_front_timestamp(message.get("created_at") or message.get("date") or message.get("timestamp"))
        if sent_at is None or sent_at < draft_created_at:
            continue
        body = message_body(message)
        if not body:
            continue
        outbound_after_draft.append((sent_at, body))

    outbound_after_draft.sort(key=lambda item: item[0])
    for sent_at, body in outbound_after_draft:
        if text_hash(body) == draft_hash:
            return DraftAdoptionResult(STATUS_EXACT_ADOPTED, sent_at=sent_at)

    if outbound_after_draft:
        return DraftAdoptionResult(STATUS_MODIFIED_OR_MANUAL, sent_at=outbound_after_draft[0][0])

    if now - draft_created_at < timedelta(hours=pending_after_hours):
        return DraftAdoptionResult(STATUS_PENDING_REVIEW)
    return DraftAdoptionResult(STATUS_NOT_SENT)


async def refresh_draft_adoptions(
    db: AsyncSession,
    *,
    since: datetime,
    limit: int = 80,
    force: bool = False,
) -> dict[str, int]:
    since = effective_since(since)
    result = await db.execute(
        select(ConversationAction)
        .where(
            ConversationAction.action_type == DRAFT_TOOL_NAME,
            ConversationAction.created_at >= since,
        )
        .order_by(ConversationAction.created_at.desc())
        .limit(limit)
    )
    actions = list(result.scalars().all())
    refreshed = 0
    skipped = 0
    failed = 0

    for action in actions:
        existing = await db.get(DraftAdoption, action.id)
        if existing and not force and existing.status in TERMINAL_STATUSES:
            skipped += 1
            continue

        draft_hash = draft_hash_from_action_key(action.action_key)
        checked_at = datetime.utcnow()
        try:
            messages = await get_conversation_messages(action.conversation_id)
            adoption = classify_draft_adoption(draft_hash, action.created_at, messages, now=checked_at)
        except Exception as exc:
            adoption = DraftAdoptionResult(STATUS_UNKNOWN, error=str(exc)[:500])
            failed += 1

        row = existing or DraftAdoption(action_id=action.id)
        row.conversation_id = action.conversation_id
        row.action_key = action.action_key
        row.draft_hash = draft_hash
        row.status = adoption.status
        row.sent_at = adoption.sent_at
        row.checked_at = checked_at
        row.error = adoption.error
        row.draft_created_at = action.created_at
        db.add(row)
        refreshed += 1

    await db.commit()
    return {"checked": len(actions), "refreshed": refreshed, "skipped": skipped, "failed": failed}


async def draft_adoption_metrics(db: AsyncSession, *, since: datetime) -> dict[str, Any]:
    since = effective_since(since)
    try:
        action_count_result = await db.execute(
            select(func.count()).select_from(ConversationAction).where(
                ConversationAction.action_type == DRAFT_TOOL_NAME,
                ConversationAction.created_at >= since,
            )
        )
        draft_actions = int(action_count_result.scalar() or 0)

        adoption_result = await db.execute(
            select(DraftAdoption).where(DraftAdoption.draft_created_at >= since)
        )
        rows = list(adoption_result.scalars().all())
    except OperationalError:
        return _empty_metrics()
    counts = {
        STATUS_EXACT_ADOPTED: 0,
        STATUS_MODIFIED_OR_MANUAL: 0,
        STATUS_NOT_SENT: 0,
        STATUS_PENDING_REVIEW: 0,
        STATUS_UNKNOWN: 0,
    }
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1

    eligible = counts[STATUS_EXACT_ADOPTED] + counts[STATUS_MODIFIED_OR_MANUAL] + counts[STATUS_NOT_SENT]
    sent_or_replied = counts[STATUS_EXACT_ADOPTED] + counts[STATUS_MODIFIED_OR_MANUAL]
    return {
        "tracking_start_at": TRACKING_START_AT.isoformat(),
        "draft_actions": draft_actions,
        "tracked_drafts": len(rows),
        "coverage_rate": _rate(len(rows), draft_actions),
        "exact_adopted": counts[STATUS_EXACT_ADOPTED],
        "modified_or_manual": counts[STATUS_MODIFIED_OR_MANUAL],
        "not_sent": counts[STATUS_NOT_SENT],
        "pending_review": counts[STATUS_PENDING_REVIEW],
        "unknown": counts[STATUS_UNKNOWN],
        "eligible_drafts": eligible,
        "direct_adoption_rate": _rate(counts[STATUS_EXACT_ADOPTED], eligible),
        "sent_or_replied_rate": _rate(sent_or_replied, eligible),
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "tracking_start_at": TRACKING_START_AT.isoformat(),
        "draft_actions": 0,
        "tracked_drafts": 0,
        "coverage_rate": 0.0,
        "exact_adopted": 0,
        "modified_or_manual": 0,
        "not_sent": 0,
        "pending_review": 0,
        "unknown": 0,
        "eligible_drafts": 0,
        "direct_adoption_rate": 0.0,
        "sent_or_replied_rate": 0.0,
    }


def _rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)
