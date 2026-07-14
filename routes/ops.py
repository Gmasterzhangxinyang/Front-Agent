import hmac
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, update

from config import settings
from database import AsyncSessionLocal
from models import ConversationAction, ConversationState, OpsReport, SybilNotification, WebhookEvent
from services.draft_adoption import draft_adoption_metrics, refresh_draft_adoptions

logger = logging.getLogger(__name__)
router = APIRouter()
STATIC_DIR = Path(__file__).resolve().parent / "static"
ATTENTION_STEPS = ("manual_review", "failed_needs_review")
FAILED_MARKERS = ("failed", "move_failed", "unknown_tool", "error")
REPORT_PERIODS = {"daily": 1, "weekly": 7, "monthly": 30}
REPORT_INTERVAL_HOURS = 3


def _require_ops_write_secret(provided: str | None) -> None:
    configured = settings.ops_write_secret
    if not configured:
        raise HTTPException(status_code=503, detail="Ops write operations are disabled")
    if not provided or not hmac.compare_digest(
        provided.encode("utf-8"),
        configured.encode("utf-8"),
    ):
        raise HTTPException(status_code=403, detail="Invalid Ops write secret")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _front_url(conversation_id: str) -> str:
    if not conversation_id:
        return ""
    return f"{settings.front_app_base_url.rstrip('/')}/{conversation_id}"


def _payload_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("summary", "reason", "route"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def _clip(value: str | None, limit: int = 180) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 12].rstrip() + " ..."


def _action_status(result: str | None) -> str:
    lowered = (result or "").lower()
    return "failed" if any(marker in lowered for marker in FAILED_MARKERS) else "ok"


def _state_to_dict(state: ConversationState) -> dict[str, Any]:
    return {
        "conversation_id": state.conversation_id,
        "front_url": _front_url(state.conversation_id),
        "sender_email": state.sender_email or "",
        "category": state.category or "uncategorized",
        "sub_type": state.sub_type or "",
        "step": state.step or "initial",
        "waiting": bool(state.waiting_since),
        "waiting_since": _iso(state.waiting_since),
        "summary": _payload_summary(state.payload),
        "payload": state.payload or {},
        "created_at": _iso(state.created_at),
        "updated_at": _iso(state.updated_at),
    }


def _action_to_dict(action: ConversationAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "conversation_id": action.conversation_id,
        "front_url": _front_url(action.conversation_id),
        "action_type": action.action_type,
        "action_key": action.action_key,
        "result": _clip(action.result, 260),
        "status": _action_status(action.result),
        "created_at": _iso(action.created_at),
    }


def _sybil_to_dict(item: SybilNotification) -> dict[str, Any]:
    status = item.status or "pending"
    error = item.error or ""
    if status == "sending" and error.startswith("digest-lease:"):
        error = ""
    return {
        "id": item.id,
        "conversation_id": item.conversation_id,
        "front_url": _front_url(item.conversation_id),
        "message": _clip(item.message, 260),
        "cc_email": item.cc_email or "",
        "handoff_type": item.handoff_type or "",
        "linear_url": item.linear_url or "",
        "status": status,
        "error": error,
        "created_at": _iso(item.created_at),
        "sent_at": _iso(item.sent_at),
    }


async def _scalar_count(db, statement) -> int:
    result = await db.execute(statement)
    return int(result.scalar() or 0)


def _attention_filter():
    return or_(
        ConversationState.step.in_(ATTENTION_STEPS),
        ConversationState.step.like("awaiting%"),
        ConversationState.waiting_since.is_not(None),
    )


def _rows_to_dict(rows) -> dict[str, int]:
    return {str(key or "unknown"): int(count or 0) for key, count in rows}


def _rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _state_search_text(state: ConversationState) -> str:
    payload = state.payload if isinstance(state.payload, dict) else {}
    return " ".join(
        [
            state.conversation_id or "",
            state.sender_email or "",
            state.category or "",
            state.sub_type or "",
            state.step or "",
            _payload_summary(payload),
            json.dumps(payload, ensure_ascii=False, default=str),
        ]
    ).lower()


def _sample_states(states: list[ConversationState], predicate, limit: int = 3) -> list[dict[str, Any]]:
    examples = []
    for state in states:
        if predicate(state):
            examples.append(_state_to_dict(state))
            if len(examples) >= limit:
                break
    return examples


def _insight(
    title: str,
    priority: str,
    detail: str,
    evidence_count: int,
    examples: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": title,
        "priority": priority,
        "detail": detail,
        "evidence_count": evidence_count,
        "examples": examples,
    }


def _top_categories(by_category: dict[str, int], limit: int = 3) -> str:
    items = sorted(by_category.items(), key=lambda item: item[1], reverse=True)[:limit]
    if not items:
        return "none"
    return ", ".join(f"{category} {count}" for category, count in items)


def _build_report_analysis(
    period_states: list[ConversationState],
    attention_states: list[ConversationState],
    metrics: dict[str, Any],
    by_category: dict[str, int],
    by_step: dict[str, int],
) -> dict[str, Any]:
    def category_count(*names: str) -> int:
        return sum(by_category.get(name, 0) for name in names)

    def has_words(*words: str):
        lowered_words = tuple(word.lower() for word in words)
        return lambda state: any(word in _state_search_text(state) for word in lowered_words)

    def in_categories(*categories: str):
        return lambda state: (state.category or "") in categories

    opportunities = []
    experience_signals = []
    operational_risks = []
    recommended_actions = []

    revenue_categories = ("business", "purchase", "partnership", "investment")
    revenue_predicate = lambda state: in_categories(*revenue_categories)(state) or has_words(
        "enterprise", "procurement", "demo", "quote", "vendor", "reseller", "partnership"
    )(state)
    revenue_states_by_id = {state.conversation_id: state for state in period_states if revenue_predicate(state)}
    revenue_states_by_id.update({state.conversation_id: state for state in attention_states if revenue_predicate(state)})
    revenue_count = len(revenue_states_by_id)
    if revenue_count:
        revenue_examples = _sample_states(list(revenue_states_by_id.values()), lambda state: True)
        opportunities.append(
            _insight(
                "Revenue and partnership demand",
                "high" if revenue_count >= 3 else "medium",
                "Business, purchase, partnership, and investment conversations indicate active commercial intent. Review these as sales or ecosystem leads, not just support workload.",
                revenue_count,
                revenue_examples,
            )
        )
        recommended_actions.append("Create a weekly lead review for business, purchase, partnership, and investment categories with Front links and owner assignment.")

    education_count = category_count("education")
    if education_count:
        education_examples = _sample_states(period_states, in_categories("education"))
        opportunities.append(
            _insight(
                "Education adoption signal",
                "medium" if education_count < 10 else "high",
                "Education plan requests show student and institution adoption. This can inform campus growth, eligibility rules, and education onboarding content.",
                education_count,
                education_examples,
            )
        )
        recommended_actions.append("Track education requests by school/domain and convert repeated schools into onboarding or campus ambassador opportunities.")

    technical_product_count = category_count("technical", "roadmap", "security", "data_export")
    if technical_product_count:
        technical_examples = _sample_states(period_states, in_categories("technical", "roadmap", "security", "data_export"))
        opportunities.append(
            _insight(
                "Product and enterprise-readiness feedback",
                "medium",
                "Technical, roadmap, security, and data export questions are direct product feedback. They often reveal missing docs, enterprise trust requirements, or features users expect.",
                technical_product_count,
                technical_examples,
            )
        )
        recommended_actions.append("Review technical and roadmap questions weekly with product/docs owners and convert repeated asks into docs or roadmap evidence.")

    account_count = category_count("account")
    if account_count:
        account_examples = _sample_states(period_states, in_categories("account"))
        experience_signals.append(
            _insight(
                "Account access friction",
                "high" if account_count >= 3 else "medium",
                "Account, login, verification, email-change, and deletion requests are user-experience friction. They should be separated from generic support because they block product access.",
                account_count,
                account_examples,
            )
        )
        recommended_actions.append("Break down account issues by subtype and fix the top blocker first, especially verification-code and identity-verification flows.")

    billing_count = category_count("billing")
    if billing_count:
        billing_examples = _sample_states(period_states, in_categories("billing"))
        experience_signals.append(
            _insight(
                "Billing and plan confusion",
                "medium",
                "Billing conversations usually point to plan, invoice, downgrade, or refund confusion. These are sensitive moments that can affect retention.",
                billing_count,
                billing_examples,
            )
        )
        recommended_actions.append("Turn repeated billing and downgrade cases into clearer in-product copy and billing help-center entries.")

    waiting_count = sum(1 for state in attention_states if state.waiting_since or (state.step or "").startswith("awaiting"))
    if waiting_count:
        waiting_examples = _sample_states(
            attention_states,
            lambda state: bool(state.waiting_since) or (state.step or "").startswith("awaiting"),
        )
        experience_signals.append(
            _insight(
                "Users are stuck waiting for next information or review",
                "high" if waiting_count >= 5 else "medium",
                "Awaiting states mean the support flow depends on missing user data or manual review. Long-lived awaiting states are a user-experience drag and can make automation look unresponsive.",
                waiting_count,
                waiting_examples,
            )
        )
        recommended_actions.append("Add a stale-awaiting review habit and improve prompts that ask users for missing information.")

    missing_sender_count = sum(1 for state in period_states if not state.sender_email)
    if missing_sender_count:
        operational_risks.append(
            _insight(
                "Sender email missing in tracked state",
                "high" if missing_sender_count >= 5 else "medium",
                "Missing sender_email reduces history quality and can weaken draft recipient safety. This is a data-quality issue in the ingestion/state path, not a customer demand signal.",
                missing_sender_count,
                _sample_states(period_states, lambda state: not state.sender_email),
            )
        )
        recommended_actions.append("Audit why sender_email is blank for recent conversations and preserve it whenever Front provides the original sender.")

    if metrics.get("current_failed", 0):
        operational_risks.append(
            _insight(
                "Failed conversations need manual repair",
                "high",
                "failed_needs_review means the handler or skill flow did not complete safely. These should be reviewed before judging automation quality from aggregate numbers.",
                int(metrics.get("current_failed", 0)),
                _sample_states(attention_states, lambda state: state.step == "failed_needs_review"),
            )
        )
        recommended_actions.append("Clear failed_needs_review daily and capture root cause as either routing bug, skill gap, or external API failure.")

    if metrics.get("pending_sybil", 0):
        operational_risks.append(
            _insight(
                "Sybil handoffs pending",
                "medium",
                "Pending Sybil notifications mean education handoffs are queued but not yet sent or cleared. This is expected before digest time, but should not accumulate.",
                int(metrics.get("pending_sybil", 0)),
                [],
            )
        )

    executive_summary = [
        f"{metrics.get('updated_conversations', 0)} tracked conversations changed in this window; {metrics.get('current_attention', 0)} currently need attention.",
        f"Top categories in the window: {_top_categories(by_category)}.",
        f"Commercial/partnership signal count: {revenue_count}; product/technical feedback signal count: {technical_product_count}.",
    ]
    if not opportunities and not experience_signals and not operational_risks:
        executive_summary.append("No strong opportunity, UX, or operational risk signal was detected from tracked data in this window.")

    decision_points = []
    if revenue_count:
        decision_points.append(
            _insight(
                "Follow the commercial leads first",
                "high" if revenue_count >= 3 else "medium",
                f"There are {revenue_count} business, purchase, partnership, investment, or enterprise-style conversations. These should be reviewed as pipeline or ecosystem opportunities before they age.",
                revenue_count,
                _sample_states(list(revenue_states_by_id.values()), lambda state: True, limit=2),
            )
        )
    if account_count or waiting_count:
        blocker_count = account_count + waiting_count
        decision_points.append(
            _insight(
                "Reduce access and waiting friction",
                "high" if blocker_count >= 5 else "medium",
                f"Account issues plus waiting states create {blocker_count} visible blockers. This is the clearest user-experience problem because users cannot move forward without staff or missing information.",
                blocker_count,
                _sample_states(attention_states, lambda state: bool(state.waiting_since) or (state.step or "").startswith("awaiting") or state.category == "account", limit=2),
            )
        )
    if technical_product_count or billing_count:
        feedback_count = technical_product_count + billing_count
        decision_points.append(
            _insight(
                "Turn repeated questions into product or docs work",
                "medium",
                f"There are {feedback_count} technical, enterprise-readiness, or billing-plan signals. These are useful inputs for docs, pricing copy, and roadmap evidence.",
                feedback_count,
                _sample_states(period_states, in_categories("technical", "roadmap", "security", "data_export", "billing"), limit=2),
            )
        )
    if metrics.get("current_failed", 0) or missing_sender_count:
        risk_count = int(metrics.get("current_failed", 0)) + missing_sender_count
        decision_points.append(
            _insight(
                "Clean up automation quality signals",
                "high" if metrics.get("current_failed", 0) else "medium",
                f"There are {risk_count} data or automation quality signals. Resolve failed_needs_review first, then investigate why sender_email is missing in tracked records.",
                risk_count,
                _sample_states(attention_states, lambda state: state.step == "failed_needs_review", limit=2),
            )
        )

    return {
        "executive_summary": executive_summary,
        "decision_points": decision_points[:3],
        "opportunities": opportunities,
        "experience_signals": experience_signals,
        "operational_risks": operational_risks,
        "recommended_actions": recommended_actions[:8],
    }



@router.get("/ops")
async def ops_page():
    return FileResponse(STATIC_DIR / "ops.html")


@router.get("/ops/api/summary")
async def ops_summary():
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stale_cutoff = datetime.utcnow() - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        total_conversations = await _scalar_count(db, select(func.count()).select_from(ConversationState))
        conversations_24h = await _scalar_count(
            db,
            select(func.count()).select_from(ConversationState).where(ConversationState.updated_at >= cutoff),
        )
        webhooks_24h = await _scalar_count(
            db,
            select(func.count()).select_from(WebhookEvent).where(WebhookEvent.processed_at >= cutoff),
        )
        actions_24h = await _scalar_count(
            db,
            select(func.count()).select_from(ConversationAction).where(ConversationAction.created_at >= cutoff),
        )
        attention_filter = _attention_filter()
        attention_count = await _scalar_count(
            db,
            select(func.count()).select_from(ConversationState).where(attention_filter),
        )
        failed_count = await _scalar_count(
            db,
            select(func.count()).select_from(ConversationState).where(ConversationState.step == "failed_needs_review"),
        )
        stale_waiting_count = await _scalar_count(
            db,
            select(func.count()).select_from(ConversationState).where(
                ConversationState.waiting_since.is_not(None),
                ConversationState.waiting_since < stale_cutoff,
            ),
        )

        step_rows = await db.execute(
            select(ConversationState.step, func.count()).group_by(ConversationState.step).order_by(func.count().desc())
        )
        category_rows = await db.execute(
            select(ConversationState.category, func.count()).group_by(ConversationState.category).order_by(func.count().desc())
        )
        action_rows = await db.execute(
            select(ConversationAction.action_type, func.count())
            .where(ConversationAction.created_at >= cutoff)
            .group_by(ConversationAction.action_type)
            .order_by(func.count().desc())
        )
        sybil_rows = await db.execute(
            select(SybilNotification.status, func.count()).group_by(SybilNotification.status).order_by(func.count().desc())
        )
        latest_webhook = await db.execute(select(func.max(WebhookEvent.processed_at)))
        latest_action = await db.execute(select(func.max(ConversationAction.created_at)))
        missing_sender_count = await _scalar_count(
            db,
            select(func.count()).select_from(ConversationState).where(
                or_(ConversationState.sender_email.is_(None), ConversationState.sender_email == "")
            ),
        )
        draft_adoption_7d = await draft_adoption_metrics(db, since=datetime.utcnow() - timedelta(days=7))
        report_rows = await db.execute(
            select(OpsReport).order_by(OpsReport.generated_at.desc()).limit(20)
        )
        reports_by_period = {}
        latest_report_at = None
        for report in report_rows.scalars().all():
            if latest_report_at is None or report.generated_at > latest_report_at:
                latest_report_at = report.generated_at
            if report.period not in reports_by_period:
                reports_by_period[report.period] = {
                    "generated_at": _iso(report.generated_at),
                    "window_start": _iso(report.window_start),
                    "window_end": _iso(report.window_end),
                }
        opportunity_rows = await db.execute(
            select(ConversationState)
            .where(ConversationState.category.in_(("business", "purchase", "partnership", "investment")))
            .order_by(ConversationState.updated_at.desc())
            .limit(6)
        )
        friction_rows = await db.execute(
            select(ConversationState.category, ConversationState.sub_type, func.count())
            .where(
                ConversationState.updated_at >= cutoff,
                ConversationState.category.in_(("account", "billing", "education", "technical")),
            )
            .group_by(ConversationState.category, ConversationState.sub_type)
            .order_by(func.count().desc())
            .limit(8)
        )
        recent_states = await db.execute(
            select(ConversationState).order_by(ConversationState.updated_at.desc()).limit(8)
        )
        recent_actions = await db.execute(
            select(ConversationAction).order_by(ConversationAction.created_at.desc()).limit(10)
        )

        scheduler_running = False
        try:
            from tasks.scheduler import scheduler

            scheduler_running = bool(scheduler.running)
        except Exception as exc:
            logger.debug("Unable to inspect scheduler state: %s", exc)

        return {
            "generated_at": _iso(datetime.utcnow()),
            "service": {
                "status": "ok",
                "scheduler_running": scheduler_running,
                "front_base_url": settings.front_app_base_url,
            },
            "metrics": {
                "total_conversations": total_conversations,
                "conversations_24h": conversations_24h,
                "webhooks_24h": webhooks_24h,
                "actions_24h": actions_24h,
                "attention_count": attention_count,
                "failed_count": failed_count,
                "stale_waiting_count": stale_waiting_count,
            },
            "by_step": {step or "unknown": count for step, count in step_rows.all()},
            "by_category": {category or "uncategorized": count for category, count in category_rows.all()},
            "actions_24h_by_type": {action or "unknown": count for action, count in action_rows.all()},
            "sybil_by_status": {status or "unknown": count for status, count in sybil_rows.all()},
            "draft_adoption_7d": draft_adoption_7d,
            "data_health": {
                "missing_sender_count": missing_sender_count,
                "latest_webhook_at": _iso(latest_webhook.scalar()),
                "latest_action_at": _iso(latest_action.scalar()),
                "latest_reports": reports_by_period,
                "next_report_due_at": _iso(latest_report_at + timedelta(hours=REPORT_INTERVAL_HOURS)) if latest_report_at else None,
            },
            "opportunity_items": [_state_to_dict(item) for item in opportunity_rows.scalars().all()],
            "top_user_frictions": [
                {
                    "key": f"{category or 'uncategorized'}:{sub_type or 'general'}",
                    "category": category or "uncategorized",
                    "sub_type": sub_type or "general",
                    "count": int(count or 0),
                }
                for category, sub_type, count in friction_rows.all()
            ],
            "recent_conversations": [_state_to_dict(item) for item in recent_states.scalars().all()],
            "recent_actions": [_action_to_dict(item) for item in recent_actions.scalars().all()],
        }


async def _build_ops_report_payload(period: str, db) -> dict[str, Any]:
    days = REPORT_PERIODS.get(period)
    if days is None:
        raise HTTPException(status_code=400, detail="period must be daily, weekly, or monthly")

    now = datetime.utcnow()
    since = now - timedelta(days=days)
    attention_filter = _attention_filter()

    total_tracked = await _scalar_count(db, select(func.count()).select_from(ConversationState))
    updated = await _scalar_count(
        db,
        select(func.count()).select_from(ConversationState).where(ConversationState.updated_at >= since),
    )
    created = await _scalar_count(
        db,
        select(func.count()).select_from(ConversationState).where(ConversationState.created_at >= since),
    )
    webhooks = await _scalar_count(
        db,
        select(func.count()).select_from(WebhookEvent).where(WebhookEvent.processed_at >= since),
    )
    actions = await _scalar_count(
        db,
        select(func.count()).select_from(ConversationAction).where(ConversationAction.created_at >= since),
    )
    current_attention = await _scalar_count(
        db,
        select(func.count()).select_from(ConversationState).where(attention_filter),
    )
    failed_current = await _scalar_count(
        db,
        select(func.count()).select_from(ConversationState).where(ConversationState.step == "failed_needs_review"),
    )
    failed_updated = await _scalar_count(
        db,
        select(func.count()).select_from(ConversationState).where(
            ConversationState.step == "failed_needs_review",
            ConversationState.updated_at >= since,
        ),
    )
    pending_sybil = await _scalar_count(
        db,
        select(func.count()).select_from(SybilNotification).where(SybilNotification.status == "pending"),
    )
    sent_sybil = await _scalar_count(
        db,
        select(func.count()).select_from(SybilNotification).where(
            SybilNotification.status == "sent",
            SybilNotification.sent_at >= since,
        ),
    )

    category_rows = await db.execute(
        select(ConversationState.category, func.count())
        .where(ConversationState.updated_at >= since)
        .group_by(ConversationState.category)
        .order_by(func.count().desc())
    )
    step_rows = await db.execute(
        select(ConversationState.step, func.count())
        .where(ConversationState.updated_at >= since)
        .group_by(ConversationState.step)
        .order_by(func.count().desc())
    )
    action_rows = await db.execute(
        select(ConversationAction.action_type, func.count())
        .where(ConversationAction.created_at >= since)
        .group_by(ConversationAction.action_type)
        .order_by(func.count().desc())
    )
    attention_rows = await db.execute(
        select(ConversationState)
        .where(attention_filter)
        .order_by(ConversationState.updated_at.desc())
        .limit(30)
    )
    period_rows = await db.execute(
        select(ConversationState)
        .where(ConversationState.updated_at >= since)
        .order_by(ConversationState.updated_at.desc())
        .limit(300)
    )

    attention_states = list(attention_rows.scalars().all())
    period_states = list(period_rows.scalars().all())
    draft_adoption = await draft_adoption_metrics(db, since=since)

    by_step = _rows_to_dict(step_rows.all())
    by_action = _rows_to_dict(action_rows.all())
    drafts = by_step.get("draft_created", 0) + by_action.get("front_create_draft", 0)
    handoffs = by_step.get("forwarded_keep_open", 0) + by_step.get("moved_inbox", 0)
    tickets = by_step.get("ticket_created", 0) + by_action.get("linear_create_ticket", 0)
    closed_spam = by_step.get("closed_spam", 0)
    handled = drafts + handoffs + tickets + closed_spam

    metrics = {
        "tracked_total": total_tracked,
        "updated_conversations": updated,
        "new_state_rows": created,
        "webhooks_processed": webhooks,
        "actions_logged": actions,
        "current_attention": current_attention,
        "current_failed": failed_current,
        "failed_updated": failed_updated,
        "pending_sybil": pending_sybil,
        "sent_sybil": sent_sybil,
        "drafts": drafts,
        "handoffs": handoffs,
        "tickets": tickets,
        "closed_spam": closed_spam,
        "handled_signal": handled,
        "attention_rate": _rate(current_attention, total_tracked),
        "failure_rate_period": _rate(failed_updated, updated),
        "draft_direct_adoption_rate": draft_adoption["direct_adoption_rate"],
        "draft_sent_or_replied_rate": draft_adoption["sent_or_replied_rate"],
    }
    by_category = _rows_to_dict(category_rows.all())
    analysis = _build_report_analysis(period_states, attention_states, metrics, by_category, by_step)

    return {
        "period": period,
        "days": days,
        "generated_at": _iso(now),
        "window_start": _iso(since),
        "window_end": _iso(now),
        "source_note": "Metrics come from local SQLite tables: conversation_states, conversation_actions, webhook_events, and sybil_notifications. They reflect conversations tracked by Front-Agent, not every message that may exist in Front.",
        "metrics": metrics,
        "draft_adoption": draft_adoption,
        "by_category": by_category,
        "by_step": by_step,
        "by_action": by_action,
        "analysis": analysis,
        "attention_items": [_state_to_dict(item) for item in attention_states[:12]],
        "recent_period_conversations": [_state_to_dict(item) for item in period_states[:12]],
    }


async def generate_ops_report(period: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        payload = await _build_ops_report_payload(period, db)
        report = OpsReport(
            period=period,
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            window_start=datetime.fromisoformat(payload["window_start"]),
            window_end=datetime.fromisoformat(payload["window_end"]),
            payload=payload,
        )
        db.add(report)
        await db.commit()
        logger.info("Generated %s ops report at %s", period, payload["generated_at"])
        return payload


async def generate_all_ops_reports() -> None:
    for period in REPORT_PERIODS:
        await generate_ops_report(period)


@router.get("/ops/api/report")
async def ops_report(period: str = "daily", fresh: bool = False):
    if period not in REPORT_PERIODS:
        raise HTTPException(status_code=400, detail="period must be daily, weekly, or monthly")

    async with AsyncSessionLocal() as db:
        if not fresh:
            result = await db.execute(
                select(OpsReport)
                .where(OpsReport.period == period)
                .order_by(OpsReport.generated_at.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if latest and latest.payload:
                return latest.payload

        payload = await _build_ops_report_payload(period, db)
        report = OpsReport(
            period=period,
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            window_start=datetime.fromisoformat(payload["window_start"]),
            window_end=datetime.fromisoformat(payload["window_end"]),
            payload=payload,
        )
        db.add(report)
        await db.commit()
        return payload


@router.post("/ops/api/draft-adoption/refresh")
async def refresh_draft_adoption(days: int = Query(default=7, ge=1, le=30), limit: int = Query(default=80, ge=1, le=300), force: bool = False):
    since = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        result = await refresh_draft_adoptions(db, since=since, limit=limit, force=force)
        metrics = await draft_adoption_metrics(db, since=since)
        return {"window_days": days, "refresh": result, "draft_adoption": metrics}


@router.get("/ops/api/conversations")
async def list_conversations(
    limit: int = Query(default=80, ge=1, le=300),
    status: str = "all",
    category: str = "",
    q: str = "",
):
    async with AsyncSessionLocal() as db:
        query = select(ConversationState).order_by(ConversationState.updated_at.desc()).limit(limit)
        if status == "attention":
            query = query.where(
                _attention_filter()
            )
        elif status and status != "all":
            query = query.where(ConversationState.step == status)
        if category:
            query = query.where(ConversationState.category == category)
        if q:
            pattern = f"%{q.strip()}%"
            query = query.where(
                or_(
                    ConversationState.conversation_id.like(pattern),
                    ConversationState.sender_email.like(pattern),
                )
            )
        result = await db.execute(query)
        items = [_state_to_dict(item) for item in result.scalars().all()]
        return {"items": items, "count": len(items)}


@router.get("/ops/api/conversations/{conversation_id}")
async def conversation_detail(conversation_id: str):
    async with AsyncSessionLocal() as db:
        state_result = await db.execute(
            select(ConversationState).where(ConversationState.conversation_id == conversation_id)
        )
        state = state_result.scalar_one_or_none()
        if not state:
            raise HTTPException(status_code=404, detail="Conversation state not found")
        action_result = await db.execute(
            select(ConversationAction)
            .where(ConversationAction.conversation_id == conversation_id)
            .order_by(ConversationAction.created_at.desc())
            .limit(80)
        )
        sybil_result = await db.execute(
            select(SybilNotification)
            .where(SybilNotification.conversation_id == conversation_id)
            .order_by(SybilNotification.created_at.desc())
        )
        return {
            "state": _state_to_dict(state),
            "actions": [_action_to_dict(item) for item in action_result.scalars().all()],
            "sybil": [_sybil_to_dict(item) for item in sybil_result.scalars().all()],
        }


@router.get("/ops/api/actions")
async def list_actions(limit: int = Query(default=100, ge=1, le=300)):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationAction).order_by(ConversationAction.created_at.desc()).limit(limit)
        )
        items = [_action_to_dict(item) for item in result.scalars().all()]
        return {"items": items, "count": len(items)}


@router.get("/ops/api/sybil")
async def list_sybil(status: str = "", limit: int = Query(default=100, ge=1, le=300)):
    async with AsyncSessionLocal() as db:
        query = select(SybilNotification).order_by(SybilNotification.created_at.desc()).limit(limit)
        if status:
            query = query.where(SybilNotification.status == status)
        result = await db.execute(query)
        items = [_sybil_to_dict(item) for item in result.scalars().all()]
        return {"items": items, "count": len(items)}


@router.delete("/ops/api/sybil/{notification_id}")
async def dismiss_sybil_notification(
    notification_id: int,
    x_ops_write_secret: str | None = Header(
        default=None,
        alias="X-Ops-Write-Secret",
    ),
):
    _require_ops_write_secret(x_ops_write_secret)

    async with AsyncSessionLocal() as db:
        item = await db.get(SybilNotification, notification_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail="Sybil notification not found",
            )
        if item.status == "dismissed":
            return {"item": _sybil_to_dict(item)}
        if item.status != "pending":
            raise HTTPException(
                status_code=409,
                detail="Only pending notifications can be dismissed",
            )

        statement = (
            update(SybilNotification)
            .where(
                SybilNotification.id == notification_id,
                SybilNotification.status == "pending",
            )
            .values(status="dismissed")
        )
        result = await db.execute(statement)
        if result.rowcount != 1:
            await db.rollback()
            current = await db.get(SybilNotification, notification_id)
            if current is not None and current.status == "dismissed":
                return {"item": _sybil_to_dict(current)}
            raise HTTPException(
                status_code=409,
                detail="Notification status changed",
            )

        db.add(
            ConversationAction(
                conversation_id=item.conversation_id,
                action_type="sybil_dismiss",
                action_key=f"notification:{notification_id}",
                result="dismissed",
            )
        )
        await db.commit()
        await db.refresh(item)
        return {"item": _sybil_to_dict(item)}
