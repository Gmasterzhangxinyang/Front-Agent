"""Internal handoff helpers implemented through Front forwarding.

These helpers never send email to the customer. They send the original Front
conversation plus an internal summary to configured Dify recipients.
"""

import logging

logger = logging.getLogger(__name__)
ALLOWED_INTERNAL_DOMAIN = "@dify.ai"


def format_summary(message: str, linear_url: str | None = None, extra: str = "") -> str:
    parts = [message.strip()]
    if linear_url:
        parts.extend(["", f"Linear: {linear_url}"])
    if extra:
        parts.extend(["", extra.strip()])
    return "\n".join(part for part in parts if part is not None).strip()


def _is_allowed_internal_recipient(value: str) -> bool:
    recipients = [item.strip().lower() for item in value.split(",") if item.strip()]
    return bool(recipients) and all(item.endswith(ALLOWED_INTERNAL_DOMAIN) for item in recipients)


async def forward_to_colleague(
    conversation_id: str,
    to_email: str,
    message: str,
    label: str,
) -> bool:
    if not conversation_id:
        logger.warning("Cannot forward colleague handoff without conversation_id")
        return False
    if not to_email:
        logger.warning("No colleague forwarding recipient configured for %s", label)
        return False
    if not _is_allowed_internal_recipient(to_email):
        logger.error("Refusing %s handoff to non-internal recipient: %s", label, to_email)
        return False
    from tools import front

    return await front.forward_conversation_direct(
        conversation_id,
        to_email,
        summary=message,
        label=label,
    )


async def forward_to_bobby(
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

    from config import settings

    return await forward_to_colleague(
        conversation_id,
        settings.internal_forward_bobby_email,
        format_summary(message, linear_url=linear_url, extra="\n\n".join(extra_parts)),
        "internal Bobby handoff",
    )


async def forward_to_limin(message: str, conversation_id: str = "") -> bool:
    from config import settings

    return await forward_to_colleague(
        conversation_id,
        settings.internal_forward_limin_email or settings.internal_forward_bobby_email,
        message,
        "account handoff to Bobby",
    )


async def forward_to_sybil(message: str, conversation_id: str = "") -> bool:
    from config import settings

    return await forward_to_colleague(
        conversation_id,
        settings.internal_forward_sybil_email,
        message,
        "education handoff",
    )
