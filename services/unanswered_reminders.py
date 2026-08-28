"""Remind Bobby when an in-scope customer email has no response after 12 hours."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.message_identity import (
    external_sender_email,
    is_external_inbound_message,
    is_internal_email,
)
from config import settings
from models import ConversationAction
from services.draft_adoption import parse_front_timestamp
from tools import feishu
from tools.front import front_request, get_conversation_comments, get_conversation_messages
from tools.state import get_action, record_action

logger = logging.getLogger(__name__)

REMINDER_AFTER_HOURS = 12
SCAN_LIMIT = 10
FRONT_FETCH_CONCURRENCY = 1
SEARCH_PAGE_LIMIT = 100
SEARCH_MAX_PAGES = 3
SLA_ACTION_TYPE = "unanswered_email_sla"
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
SUPPORT_INBOX_ID = "inb_f9fvf"
# The watchdog started on 2026-08-28 China time. Earlier customer messages are
# historical backlog and must never generate reminders.
SLA_START_AT_UTC = datetime(2026, 8, 27, 16, 0, 0)


@dataclass(frozen=True)
class UnansweredDecision:
    latest_customer_message: dict[str, Any] | None
    latest_customer_at: datetime | None
    customer_replied: bool = False
    bobby_commented: bool = False

    @property
    def handled(self) -> bool:
        return self.customer_replied or self.bobby_commented


def _timestamp(item: dict[str, Any]) -> datetime | None:
    return parse_front_timestamp(
        item.get("posted_at")
        or item.get("created_at")
        or item.get("updated_at")
    )


def _contact_email(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        return str(value.get("handle") or value.get("email") or "").strip().lower()
    return ""


def _has_external_recipient(message: dict[str, Any]) -> bool:
    for recipient in message.get("recipients") or []:
        if not isinstance(recipient, dict):
            continue
        if str(recipient.get("role") or "").lower() not in {"to", "cc", "bcc"}:
            continue
        email = _contact_email(recipient)
        if email and not is_internal_email(email):
            return True
    return False


def _is_sent_customer_reply(message: dict[str, Any]) -> bool:
    return (
        message.get("type") == "email"
        and message.get("is_inbound") is False
        and message.get("is_draft") is not True
        and _has_external_recipient(message)
    )


def _is_bobby_comment(comment: dict[str, Any]) -> bool:
    author = comment.get("author") or {}
    author_id = str(author.get("id") or "").strip()
    author_email = _contact_email(author)
    configured_emails = {
        settings.feishu_bobby_email.strip().lower(),
        settings.internal_forward_bobby_email.strip().lower(),
    }
    return bool(
        (settings.front_teammate_bobby and author_id == settings.front_teammate_bobby)
        or (author_email and author_email in configured_emails)
    )


def _is_assigned_to_bobby(conversation: dict[str, Any]) -> bool:
    assignee = conversation.get("assignee") or {}
    return bool(
        (
            settings.front_teammate_bobby
            and str(assignee.get("id") or "") == settings.front_teammate_bobby
        )
        or (
            _contact_email(assignee)
            and _contact_email(assignee)
            == settings.feishu_bobby_email.strip().lower()
        )
    )


def evaluate_unanswered_timeline(
    messages: list[dict[str, Any]],
    comments: list[dict[str, Any]],
) -> UnansweredDecision:
    inbound: list[tuple[datetime, dict[str, Any]]] = []
    for message in messages:
        created_at = _timestamp(message)
        if is_external_inbound_message(message) and created_at is not None:
            inbound.append((created_at, message))
    if not inbound:
        return UnansweredDecision(None, None)

    latest_at, latest_message = max(inbound, key=lambda item: item[0])
    customer_replied = any(
        _is_sent_customer_reply(message)
        and (created_at := _timestamp(message)) is not None
        and created_at > latest_at
        for message in messages
    )
    bobby_commented = any(
        _is_bobby_comment(comment)
        and (created_at := _timestamp(comment)) is not None
        and created_at > latest_at
        for comment in comments
    )
    return UnansweredDecision(
        latest_message,
        latest_at,
        customer_replied=customer_replied,
        bobby_commented=bobby_commented,
    )


def _message_action_key(message: dict[str, Any], created_at: datetime) -> str:
    message_id = str(message.get("id") or "").strip()
    if message_id:
        return f"message:{message_id}"
    fingerprint = "|".join(
        (created_at.isoformat(), external_sender_email(message), str(message.get("subject") or ""))
    )
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    return f"fingerprint:{digest}"


def _conversation_is_open(conversation: dict[str, Any]) -> bool:
    category = str(conversation.get("status_category") or "").strip().lower()
    if category:
        return category == "open"
    return str(conversation.get("status") or "").strip().lower() in {
        "assigned",
        "unassigned",
        "open",
    }


def is_china_weekday(now: datetime) -> bool:
    if now.tzinfo is None:
        aware = now.replace(tzinfo=timezone.utc)
    else:
        aware = now.astimezone(timezone.utc)
    return aware.astimezone(CHINA_TIMEZONE).weekday() < 5


def _one_line(value: Any, fallback: str) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized[:180] if normalized else fallback


def build_reminder_text(
    conversation: dict[str, Any],
    decision: UnansweredDecision,
    *,
    now: datetime,
) -> str:
    assert decision.latest_customer_message is not None
    assert decision.latest_customer_at is not None
    message = decision.latest_customer_message
    sender = (
        external_sender_email(message)
        or _contact_email(conversation.get("recipient") or {})
        or "未知客户"
    )
    subject = message.get("subject") or conversation.get("subject")
    waiting_hours = max(
        REMINDER_AFTER_HOURS,
        int((now - decision.latest_customer_at).total_seconds() // 3600),
    )
    conversation_id = str(conversation.get("id") or "")
    front_url = f"{settings.front_app_base_url.rstrip('/')}/{conversation_id}"
    return "\n".join(
        (
            "⏰ Front 邮件超过 12 小时未回复",
            f"客户：{_one_line(sender, '未知客户')}",
            f"主题：{_one_line(subject, '（无主题）')}",
            f"已等待：约 {waiting_hours} 小时",
            f"Front：{front_url}",
        )
    )


def _next_page_token(payload: dict[str, Any]) -> str | None:
    next_url = (payload.get("_pagination") or {}).get("next")
    if not next_url:
        return None
    return (parse_qs(urlparse(next_url).query).get("page_token") or [None])[0]


async def _search_open_conversations(query: str) -> list[dict[str, Any]]:
    encoded_query = quote(query, safe="")
    url = f"https://api2.frontapp.com/conversations/search/{encoded_query}"
    conversations: list[dict[str, Any]] = []
    page_token: str | None = None
    for _ in range(SEARCH_MAX_PAGES):
        params: dict[str, Any] = {"limit": SEARCH_PAGE_LIMIT}
        if page_token:
            params["page_token"] = page_token
        response = await front_request("GET", url, params=params)
        response.raise_for_status()
        payload = response.json()
        conversations.extend(payload.get("_results") or [])
        page_token = _next_page_token(payload)
        if not page_token:
            break
    return conversations


async def _last_sla_checks(
    db: AsyncSession,
    conversation_ids: list[str],
) -> dict[str, datetime]:
    if not conversation_ids:
        return {}
    result = await db.execute(
        select(
            ConversationAction.conversation_id,
            func.max(ConversationAction.created_at),
        )
        .where(
            ConversationAction.conversation_id.in_(conversation_ids),
            ConversationAction.action_type == SLA_ACTION_TYPE,
        )
        .group_by(ConversationAction.conversation_id)
    )
    return {
        conversation_id: checked_at
        for conversation_id, checked_at in result.all()
        if checked_at is not None
    }


async def _candidate_conversations(
    db: AsyncSession,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    support_result, assigned_result = await asyncio.gather(
        _search_open_conversations(f"inbox:{SUPPORT_INBOX_ID} is:open"),
        _search_open_conversations(
            f"assignee:{settings.front_teammate_bobby} is:open"
        ),
        return_exceptions=True,
    )

    errors = 0
    support: list[dict[str, Any]] = []
    assigned: list[dict[str, Any]] = []
    if isinstance(support_result, BaseException):
        errors += 1
        logger.error("Failed to search open Support conversations: %r", support_result)
    else:
        support = [item for item in support_result if _conversation_is_open(item)]
    if isinstance(assigned_result, BaseException):
        errors += 1
        logger.error("Failed to search Bobby-assigned conversations: %r", assigned_result)
    else:
        assigned = [
            item
            for item in assigned_result
            if _conversation_is_open(item) and _is_assigned_to_bobby(item)
        ]

    combined = {
        str(item.get("id")): item
        for item in [*support, *assigned]
        if item.get("id")
    }
    ordered = sorted(
        combined.values(),
        key=lambda item: _timestamp(item) or datetime.min,
        reverse=True,
    )
    checks = await _last_sla_checks(db, list(combined))
    fresh: list[dict[str, Any]] = []
    for conversation in ordered:
        conversation_id = str(conversation.get("id") or "")
        updated_at = _timestamp(conversation)
        last_check_at = checks.get(conversation_id)
        if (
            updated_at is not None
            and last_check_at is not None
            and last_check_at >= updated_at
        ):
            continue
        fresh.append(conversation)

    return (
        fresh[: max(1, min(limit, SCAN_LIMIT))],
        {
            "source_support": len(support),
            "source_assigned": len(assigned),
            "source_union": len(combined),
        },
        errors,
    )


async def _front_snapshot(
    conversation: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conversation_id = str(conversation.get("id") or "")
    async with semaphore:
        messages, comments = await asyncio.gather(
            get_conversation_messages(conversation_id),
            get_conversation_comments(conversation_id),
        )
    return messages, comments


async def _record_terminal_check(
    db: AsyncSession,
    conversation_id: str,
    action_key: str,
    status: str,
) -> None:
    await record_action(
        db,
        conversation_id,
        SLA_ACTION_TYPE,
        action_key,
        json.dumps({"status": status}, ensure_ascii=False),
    )


async def scan_unanswered_conversations(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = SCAN_LIMIT,
    dry_run: bool = False,
) -> dict[str, int]:
    current = (now or datetime.utcnow()).replace(tzinfo=None)
    stats = {
        "source_support": 0,
        "source_assigned": 0,
        "source_union": 0,
        "selected": 0,
        "due": 0,
        "reminded": 0,
        "replied": 0,
        "bobby_commented": 0,
        "before_start": 0,
        "not_due": 0,
        "closed": 0,
        "duplicates": 0,
        "errors": 0,
        "skipped_non_workday": 0,
    }
    if not is_china_weekday(current):
        stats["skipped_non_workday"] = 1
        return stats

    conversations, source_stats, search_errors = await _candidate_conversations(
        db,
        limit=limit,
    )
    stats.update(source_stats)
    stats["selected"] = len(conversations)
    stats["errors"] += search_errors

    semaphore = asyncio.Semaphore(FRONT_FETCH_CONCURRENCY)
    snapshots = await asyncio.gather(
        *(_front_snapshot(conversation, semaphore) for conversation in conversations),
        return_exceptions=True,
    )

    for conversation, snapshot in zip(conversations, snapshots):
        conversation_id = str(conversation.get("id") or "")
        if isinstance(snapshot, BaseException):
            stats["errors"] += 1
            logger.error(
                "Failed to load Front timeline for %s: %r",
                conversation_id,
                snapshot,
            )
            continue
        try:
            messages, comments = snapshot
            decision = evaluate_unanswered_timeline(messages, comments)
            if decision.latest_customer_message is None or decision.latest_customer_at is None:
                stats["not_due"] += 1
                continue

            action_key = _message_action_key(
                decision.latest_customer_message,
                decision.latest_customer_at,
            )
            if await get_action(db, conversation_id, SLA_ACTION_TYPE, action_key):
                stats["duplicates"] += 1
                continue
            if decision.latest_customer_at < SLA_START_AT_UTC:
                stats["before_start"] += 1
                if not dry_run:
                    await _record_terminal_check(
                        db,
                        conversation_id,
                        action_key,
                        "ignored_before_start",
                    )
                continue
            if not _conversation_is_open(conversation):
                stats["closed"] += 1
                if not dry_run:
                    await _record_terminal_check(
                        db, conversation_id, action_key, "conversation_closed"
                    )
                continue
            if decision.customer_replied:
                stats["replied"] += 1
                if not dry_run:
                    await _record_terminal_check(
                        db, conversation_id, action_key, "customer_replied"
                    )
                continue
            if decision.bobby_commented:
                stats["bobby_commented"] += 1
                if not dry_run:
                    await _record_terminal_check(
                        db, conversation_id, action_key, "bobby_commented"
                    )
                continue
            if current - decision.latest_customer_at < timedelta(hours=REMINDER_AFTER_HOURS):
                stats["not_due"] += 1
                continue

            stats["due"] += 1
            if dry_run:
                continue
            reminder = build_reminder_text(conversation, decision, now=current)
            if await feishu.send_bobby_personal_text(reminder):
                await _record_terminal_check(
                    db, conversation_id, action_key, "reminded"
                )
                stats["reminded"] += 1
            else:
                stats["errors"] += 1
        except Exception:
            stats["errors"] += 1
            logger.exception(
                "Failed to check unanswered SLA for %s",
                conversation_id,
            )
    return stats
