from dataclasses import dataclass, field
from typing import Any

from agent.classification import ClassificationResult, should_auto_close_spam


@dataclass(frozen=True)
class RouteDecision:
    name: str
    handled_before_skill: bool
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    state_category: str | None = None
    state_sub_type: str | None = None
    state_step: str = "done"
    waiting: bool = False
    keep_open: bool = True
    send_feedback_comment: bool = True
    close_conversation: bool = False
    customer_action: str = "skill_policy"
    internal_target: str | None = None
    inbox_target: str | None = None
    reason: str = ""


def decide_initial_route(
    classification: ClassificationResult,
    conversation_id: str,
    sender_email: str,
) -> RouteDecision:
    """Return deterministic side-effect routing before the skill agent loop.

    Confidence is intentionally not used as a routing threshold. It is an
    observation field for review and offline evaluation only.
    """
    category = classification.category
    sub_type = classification.sub_type
    summary = classification.summary or "No summary provided by classifier."

    if should_auto_close_spam(classification):
        return RouteDecision(
            name="spam_auto_close",
            handled_before_skill=True,
            tool_name="front_close_conversation",
            tool_args={"conversation_id": conversation_id},
            state_category="spam",
            state_sub_type=None,
            state_step="closed_spam",
            waiting=False,
            keep_open=False,
            send_feedback_comment=False,
            close_conversation=True,
            customer_action="none",
            reason="Clear spam, ads, or unsolicited promotion can be archived automatically.",
        )

    if category == "unclear":
        return RouteDecision(
            name="manual_review_bobby",
            handled_before_skill=True,
            tool_name="front_forward_to_bobby",
            tool_args={
                "conversation_id": conversation_id,
                "message": _manual_review_message(classification, sender_email),
            },
            state_category=category,
            state_sub_type=sub_type,
            state_step="manual_review",
            waiting=False,
            keep_open=True,
            customer_action="none",
            internal_target="bobby@dify.ai",
            reason="Classifier returned unclear or route cannot be safely determined by rules.",
        )

    if category == "security":
        return RouteDecision(
            name="security_move_inbox",
            handled_before_skill=True,
            tool_name="front_forward_to_security",
            tool_args={"conversation_id": conversation_id},
            state_category="security",
            state_sub_type=sub_type,
            state_step="moved_inbox",
            waiting=False,
            keep_open=True,
            customer_action="none",
            inbox_target="Security",
            reason="Security reports move to the Security inbox for review.",
        )

    if category in {"partnership", "marketing"}:
        tool_name = "front_forward_to_community" if category == "partnership" else "front_forward_to_partnerships"
        args = {
            "conversation_id": conversation_id,
            "summary": summary,
        }
        if tool_name == "front_forward_to_community":
            args["region"] = "plugins_templates"
        return RouteDecision(
            name="marketing_forwarded_keep_open",
            handled_before_skill=True,
            tool_name=tool_name,
            tool_args=args,
            state_category=category,
            state_sub_type=sub_type,
            state_step="forwarded_keep_open",
            waiting=False,
            keep_open=True,
            customer_action="none",
            internal_target="marketing@dify.ai",
            reason="Marketplace, community, plugin ecosystem, and external cooperation route to marketing@dify.ai.",
        )

    return RouteDecision(
        name="skill_flow",
        handled_before_skill=False,
        state_category=category,
        state_sub_type=sub_type,
        state_step="skill_in_progress",
        keep_open=True,
        customer_action="skill_policy",
        reason="Route requires skill-specific policy and templates.",
    )


def _manual_review_message(classification: ClassificationResult, sender_email: str) -> str:
    lines = [
        "邮件分类不确定，请人工判断。",
        f"发件人: {sender_email}",
        f"AI 猜测: {classification.category}/{classification.sub_type}",
    ]
    if classification.confidence:
        lines.append(f"置信度(仅供参考): {classification.confidence:.0%}")
    if classification.summary:
        lines.append(f"摘要: {classification.summary}")
    if classification.evidence:
        lines.append("证据: " + "; ".join(classification.evidence[:3]))
    return "\n".join(lines)
