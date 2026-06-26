import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationState


MAX_CANDIDATES = 300
MAX_TEXT = 220
MIN_CLASSIFICATION_OVERLAP = 3
MIN_CATEGORY_OVERLAP = 2
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "you",
    "your",
    "are",
    "can",
    "have",
    "has",
    "not",
    "but",
    "email",
    "user",
    "dify",
    "please",
    "support",
    "problem",
    "issue",
    "question",
    "request",
}


@dataclass(frozen=True)
class CaseMemoryItem:
    category: str
    sub_type: str
    step: str
    summary: str
    reason: str
    outcome: str
    score: int = 0


def tokenize(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-zA-Z0-9_\-]{3,}|[\u4e00-\u9fff]{2,}", text.lower()):
        cleaned = token.strip("-_")
        if cleaned and cleaned not in STOPWORDS:
            tokens.add(cleaned)
    return tokens


def score_case(query: str, item: CaseMemoryItem, category: str | None = None) -> int:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0

    case_text = " ".join([item.category, item.sub_type, item.summary, item.reason])
    overlap_count = len(query_tokens & tokenize(case_text))
    min_overlap = MIN_CATEGORY_OVERLAP if category else MIN_CLASSIFICATION_OVERLAP
    if overlap_count < min_overlap:
        return 0

    score = overlap_count
    if category and item.category == category:
        score += 2
    if item.step in {"done", "draft_created", "closed_spam", "moved_inbox", "forwarded_keep_open"}:
        score += 1
    if item.step in {"failed_needs_review", "manual_review"} or item.step.startswith("awaiting"):
        score += 1
    return score


def build_case_memory_prompt(items: list[CaseMemoryItem]) -> str:
    if not items:
        return ""

    lines = [
        "Historical case memory (reference only; deterministic routing and skill safety rules still win):",
        "- Use these as hints for ambiguity, missing facts, likely subtype, and known failure modes.",
        "- Do not expose case details, case ids, internal notes, or personal data to the customer.",
        "- Do not copy an old outcome blindly; apply the current skill and route policy.",
    ]
    for item in items:
        parts = [f"{item.category}/{item.sub_type or 'general'}", f"step={item.step}", item.outcome]
        if item.summary:
            parts.append(f"signal={_clip(_redact(item.summary))}")
        if item.reason:
            parts.append(f"note={_clip(_redact(item.reason))}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


async def build_case_memory_context(
    db: AsyncSession,
    query: str,
    *,
    category: str | None = None,
    limit: int = 4,
) -> str:
    result = await db.execute(
        select(ConversationState)
        .order_by(ConversationState.updated_at.desc())
        .limit(MAX_CANDIDATES)
    )
    candidates = []
    for state in result.scalars().all():
        item = _state_to_item(state)
        if category and item.category != category:
            continue
        score = score_case(query, item, category=category)
        if score > 0:
            candidates.append(CaseMemoryItem(**{**item.__dict__, "score": score}))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return build_case_memory_prompt(candidates[:limit])


def _state_to_item(state: ConversationState) -> CaseMemoryItem:
    payload = state.payload if isinstance(state.payload, dict) else {}
    summary = _first_payload_text(payload, "summary", "request", "issue", "assessment", "school_name")
    reason = _first_payload_text(payload, "reason", "route", "tool_result", "fallback_result")
    return CaseMemoryItem(
        category=state.category or "unclear",
        sub_type=state.sub_type or "",
        step=state.step or "initial",
        summary=summary,
        reason=reason,
        outcome=_outcome_for_step(state.step or ""),
    )


def _first_payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, default=str)
            return str(value)
    return ""


def _outcome_for_step(step: str) -> str:
    if step == "failed_needs_review":
        return "previously failed; prefer manual review or safer tool sequence"
    if step == "manual_review":
        return "previously required Bobby/manual review"
    if step.startswith("awaiting"):
        return "previously needed missing information before resolving"
    if step == "closed_spam":
        return "previously closed as spam"
    if step == "moved_inbox":
        return "previously moved to the owner inbox"
    if step == "forwarded_keep_open":
        return "previously forwarded internally and kept open"
    if step == "draft_created":
        return "previously handled with a customer draft"
    if step == "done":
        return "previously completed"
    return "previously tracked"


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 4].rstrip() + " ..."


def _redact(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"\b(?:\+?\d[\d\-\s()]{7,}\d)\b", "[phone]", text)
    return text
