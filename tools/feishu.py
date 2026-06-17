"""Front forwarding compatibility layer.

The historical notification tool names and module path are kept for LLM schema
and skill compatibility. New stable-agent code forwards the Front conversation
to configured colleague email addresses through Front.
"""

import logging

from config import settings
from tools import front

logger = logging.getLogger(__name__)


def _format_summary(message: str, linear_url: str | None = None, extra: str = "") -> str:
    parts = [message.strip()]
    if linear_url:
        parts.extend(["", f"Linear: {linear_url}"])
    if extra:
        parts.extend(["", extra.strip()])
    return "\n".join(parts).strip()


async def _forward_to_colleague(
    conversation_id: str,
    to_email: str,
    message: str,
    label: str,
) -> bool:
    if not conversation_id:
        logger.warning("Cannot forward colleague notification without conversation_id")
        return False
    if not to_email:
        logger.warning("No colleague forwarding recipient configured for %s", label)
        return False
    return await front.forward_conversation_direct(
        conversation_id,
        to_email,
        summary=message,
        label=label,
    )


async def notify_bobby(
    message: str,
    conversation_id: str = "",
    linear_url: str | None = None,
    notification_type: str = "general",
    classification_options: list[dict] | None = None,
    email_summary: str | None = None,
) -> bool:
    extra_parts = []
    if notification_type == "classify" and classification_options:
        labels = [f"- {opt.get('label') or opt.get('category')}" for opt in classification_options]
        extra_parts.append("Classification options:\n" + "\n".join(labels))
    if email_summary:
        extra_parts.append(f"Email summary: {email_summary}")

    return await _forward_to_colleague(
        conversation_id,
        settings.internal_forward_bobby_email,
        _format_summary(message, linear_url=linear_url, extra="\n\n".join(extra_parts)),
        "internal Bobby notification",
    )


async def notify_limin(message: str, conversation_id: str = "") -> bool:
    return await _forward_to_colleague(
        conversation_id,
        settings.internal_forward_limin_email or settings.internal_forward_bobby_email,
        message,
        "account handoff to Bobby",
    )


async def notify_sybil(message: str, conversation_id: str = "") -> bool:
    return await _forward_to_colleague(
        conversation_id,
        settings.internal_forward_sybil_email,
        message,
        "education handoff",
    )
