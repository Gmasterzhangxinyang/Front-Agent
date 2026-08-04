import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.message_identity import is_internal_email, message_author_email
from models import ConversationAction, ConversationState, DraftAdoption
from tools.front import (
    get_conversation,
    get_conversation_comments,
    get_conversation_messages,
)

DRAFT_TOOL_NAME = "front_create_draft"
STATUS_EXACT_ADOPTED = "exact_adopted"
STATUS_MODIFIED_OR_MANUAL = "modified_or_manual"
# Legacy value retained so old rows can be recognized and reclassified.
STATUS_NOT_SENT = "not_sent"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_HANDLED_WITHOUT_SEND = "handled_without_send"
STATUS_WAITING = "waiting"
STATUS_NO_FOLLOWUP = "no_followup_detected"
STATUS_UNKNOWN = "unknown"
# A reply classification is stable. Every no-reply/workflow status must remain
# refreshable because a teammate can reply, comment, or create a ticket later.
TERMINAL_STATUSES = {STATUS_EXACT_ADOPTED, STATUS_MODIFIED_OR_MANUAL}
PENDING_AFTER_HOURS = 24
# Start measuring draft adoption from the rollout point; older drafts were not tracked consistently.
TRACKING_START_AT = datetime(2026, 7, 7, 9, 49, 38)
WAITING_COMMENT_PATTERN = re.compile(
    r"(?:\b(?:awaiting|waiting|pending|asking)\b|等待|待确认|确认中|核实中)",
    re.IGNORECASE,
)
# Historical internal forwards polluted some real customer sender emails with
# @dify.ai, so test exclusions must use explicit conversation IDs rather than
# sender domains.
METRIC_EXCLUDED_CONVERSATION_IDS = {"cnv_1j36t6hn"}


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
        # Front can label a teammate's reply inside an internally forwarded
        # thread as inbound. An explicit internal author is more reliable than
        # that direction flag. Forward envelopes without an author remain
        # excluded and are handled through workflow evidence instead.
        return is_internal_email(message_author_email(message))
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
    comments: list[dict[str, Any]] | None = None,
    workflow_actions: set[str] | None = None,
    state_step: str = "",
    waiting_since: datetime | None = None,
    conversation_status: str = "",
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

    manual_comments_after_draft: list[tuple[datetime, str]] = []
    for comment in comments or []:
        posted_at = parse_front_timestamp(
            comment.get("posted_at") or comment.get("created_at")
        )
        body = normalize_text(comment.get("body"))
        if posted_at is None or posted_at < draft_created_at:
            continue
        # This comment is automatically added immediately before every AI
        # draft and is not evidence that a teammate handled the case.
        if body.startswith("[AI草稿]"):
            continue
        manual_comments_after_draft.append((posted_at, body))

    if manual_comments_after_draft:
        _, latest_comment = max(manual_comments_after_draft, key=lambda item: item[0])
        if WAITING_COMMENT_PATTERN.search(latest_comment):
            return DraftAdoptionResult(STATUS_WAITING)
        return DraftAdoptionResult(STATUS_HANDLED_WITHOUT_SEND)

    if workflow_actions:
        return DraftAdoptionResult(STATUS_HANDLED_WITHOUT_SEND)

    normalized_step = (state_step or "").strip().lower()
    if normalized_step in {
        "done",
        "forwarded_keep_open",
        "moved_inbox",
        "ticket_created",
        "closed_spam",
    }:
        return DraftAdoptionResult(STATUS_HANDLED_WITHOUT_SEND)

    if (
        waiting_since is not None
        or normalized_step.startswith("awaiting")
        or normalized_step in {"manual_review", "skill_in_progress"}
        or (conversation_status or "").strip().lower()
        in {"assigned", "unassigned", "open", "waiting"}
    ):
        return DraftAdoptionResult(STATUS_WAITING)

    if now - draft_created_at < timedelta(hours=pending_after_hours):
        return DraftAdoptionResult(STATUS_PENDING_REVIEW)
    return DraftAdoptionResult(STATUS_NO_FOLLOWUP)


async def _workflow_evidence(
    db: AsyncSession,
    action: ConversationAction,
) -> tuple[ConversationState | None, set[str]]:
    state = await db.get(ConversationState, action.conversation_id)
    result = await db.execute(
        select(ConversationAction.action_type).where(
            ConversationAction.conversation_id == action.conversation_id,
            ConversationAction.created_at >= action.created_at,
            ConversationAction.id != action.id,
            ConversationAction.action_type != DRAFT_TOOL_NAME,
        )
    )
    action_types = {str(value) for value in result.scalars().all() if value}
    return state, action_types


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
    # Do not hold a SQLite read transaction while calling Front.
    await db.commit()
    refreshed = 0
    skipped = 0
    failed = 0
    messages_by_conversation: dict[str, list[dict[str, Any]]] = {}
    comments_by_conversation: dict[str, list[dict[str, Any]]] = {}
    conversations_by_conversation: dict[str, dict[str, Any]] = {}

    for action in actions:
        existing = await db.get(DraftAdoption, action.id)
        is_terminal = bool(
            existing
            and not force
            and existing.status in TERMINAL_STATUSES
        )
        # A lookup starts a transaction; release it before network I/O.
        await db.commit()
        if is_terminal:
            skipped += 1
            continue

        draft_hash = draft_hash_from_action_key(action.action_key)
        checked_at = datetime.utcnow()
        try:
            messages = messages_by_conversation.get(action.conversation_id)
            if messages is None:
                messages = await get_conversation_messages(action.conversation_id)
                messages_by_conversation[action.conversation_id] = messages

            adoption = classify_draft_adoption(
                draft_hash,
                action.created_at,
                messages,
                now=checked_at,
            )
            if adoption.status not in TERMINAL_STATUSES:
                state, workflow_actions = await _workflow_evidence(db, action)
                # Release the SQLite read transaction before Front network I/O.
                await db.commit()
                state_step = state.step if state else ""
                waiting_since = state.waiting_since if state else None
                adoption = classify_draft_adoption(
                    draft_hash,
                    action.created_at,
                    messages,
                    now=checked_at,
                    workflow_actions=workflow_actions,
                    state_step=state_step,
                    waiting_since=waiting_since,
                )

                if adoption.status not in {
                    STATUS_HANDLED_WITHOUT_SEND,
                    STATUS_WAITING,
                }:
                    if action.conversation_id not in comments_by_conversation:
                        comments_by_conversation[action.conversation_id] = (
                            await get_conversation_comments(action.conversation_id)
                        )
                    comments = comments_by_conversation[action.conversation_id]
                    adoption = classify_draft_adoption(
                        draft_hash,
                        action.created_at,
                        messages,
                        now=checked_at,
                        comments=comments,
                        workflow_actions=workflow_actions,
                        state_step=state_step,
                        waiting_since=waiting_since,
                    )

                if adoption.status not in {
                    STATUS_HANDLED_WITHOUT_SEND,
                    STATUS_WAITING,
                }:
                    if action.conversation_id not in conversations_by_conversation:
                        conversations_by_conversation[action.conversation_id] = (
                            await get_conversation(action.conversation_id)
                        )
                    conversation = conversations_by_conversation[
                        action.conversation_id
                    ]
                    adoption = classify_draft_adoption(
                        draft_hash,
                        action.created_at,
                        messages,
                        now=checked_at,
                        comments=comments,
                        workflow_actions=workflow_actions,
                        state_step=state_step,
                        waiting_since=waiting_since,
                        conversation_status=conversation.get("status") or "",
                    )
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
        await db.commit()
        refreshed += 1

    return {"checked": len(actions), "refreshed": refreshed, "skipped": skipped, "failed": failed}


async def draft_adoption_metrics(
    db: AsyncSession,
    *,
    since: datetime,
    category: str | None = None,
) -> dict[str, Any]:
    since = effective_since(since)
    try:
        non_test_conversation = ~ConversationState.conversation_id.like(
            "cnv_test_%"
        )
        not_known_test_conversation = ~ConversationState.conversation_id.in_(
            METRIC_EXCLUDED_CONVERSATION_IDS
        )
        action_query = (
            select(func.count())
            .select_from(ConversationAction)
            .join(
                ConversationState,
                ConversationState.conversation_id
                == ConversationAction.conversation_id,
            )
            .where(
                ConversationAction.action_type == DRAFT_TOOL_NAME,
                ConversationAction.created_at >= since,
                non_test_conversation,
                not_known_test_conversation,
            )
        )
        adoption_query = (
            select(DraftAdoption)
            .join(
                ConversationState,
                ConversationState.conversation_id
                == DraftAdoption.conversation_id,
            )
            .where(
                DraftAdoption.draft_created_at >= since,
                non_test_conversation,
                not_known_test_conversation,
            )
        )
        if category:
            action_query = action_query.where(
                ConversationState.category == category
            )
            adoption_query = adoption_query.where(
                ConversationState.category == category
            )

        action_count_result = await db.execute(action_query)
        draft_actions = int(action_count_result.scalar() or 0)
        adoption_result = await db.execute(adoption_query)
        rows = list(adoption_result.scalars().all())
    except OperationalError:
        return _empty_metrics()
    counts = {
        STATUS_EXACT_ADOPTED: 0,
        STATUS_MODIFIED_OR_MANUAL: 0,
        STATUS_NOT_SENT: 0,
        STATUS_PENDING_REVIEW: 0,
        STATUS_HANDLED_WITHOUT_SEND: 0,
        STATUS_WAITING: 0,
        STATUS_NO_FOLLOWUP: 0,
        STATUS_UNKNOWN: 0,
    }
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1

    responded = counts[STATUS_EXACT_ADOPTED] + counts[STATUS_MODIFIED_OR_MANUAL]
    handled = responded + counts[STATUS_HANDLED_WITHOUT_SEND]
    no_followup = counts[STATUS_NO_FOLLOWUP] + counts[STATUS_NOT_SENT]
    return {
        "tracking_start_at": TRACKING_START_AT.isoformat(),
        "draft_actions": draft_actions,
        "tracked_drafts": len(rows),
        "coverage_rate": _rate(len(rows), draft_actions),
        "exact_adopted": counts[STATUS_EXACT_ADOPTED],
        "modified_or_manual": counts[STATUS_MODIFIED_OR_MANUAL],
        "responded_drafts": responded,
        "handled_without_send": counts[STATUS_HANDLED_WITHOUT_SEND],
        "waiting": counts[STATUS_WAITING],
        "no_followup_detected": no_followup,
        "not_sent": counts[STATUS_NOT_SENT],
        "pending_review": counts[STATUS_PENDING_REVIEW],
        "unknown": counts[STATUS_UNKNOWN],
        # Backward-compatible alias for existing dashboard clients.
        "eligible_drafts": responded,
        "direct_adoption_rate": _rate(counts[STATUS_EXACT_ADOPTED], responded),
        "response_detected_rate": _rate(responded, len(rows)),
        "handled_rate": _rate(handled, len(rows)),
        "sent_or_replied_rate": _rate(responded, len(rows)),
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "tracking_start_at": TRACKING_START_AT.isoformat(),
        "draft_actions": 0,
        "tracked_drafts": 0,
        "coverage_rate": 0.0,
        "exact_adopted": 0,
        "modified_or_manual": 0,
        "responded_drafts": 0,
        "handled_without_send": 0,
        "waiting": 0,
        "no_followup_detected": 0,
        "not_sent": 0,
        "pending_review": 0,
        "unknown": 0,
        "eligible_drafts": 0,
        "direct_adoption_rate": 0.0,
        "response_detected_rate": 0.0,
        "handled_rate": 0.0,
        "sent_or_replied_rate": 0.0,
    }


def _rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)
