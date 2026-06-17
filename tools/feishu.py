"""Email notification compatibility layer.

The historical notification tool names and module path are kept for LLM schema
and skill compatibility. New stable-agent code routes those calls to SMTP email
notifications only.
"""

from tools import email_notify


async def notify_bobby(
    message: str,
    conversation_id: str = "",
    linear_url: str | None = None,
    notification_type: str = "general",
    classification_options: list[dict] | None = None,
    email_summary: str | None = None,
) -> bool:
    footer_parts = []
    if linear_url:
        footer_parts.append(f"Linear: {linear_url}")
    if notification_type == "classify" and classification_options:
        labels = [f"- {opt.get('label') or opt.get('category')}" for opt in classification_options]
        footer_parts.append("Classification options:\n" + "\n".join(labels))
        footer_parts.append("Review and handle this conversation manually in Front.")
    if notification_type == "reply_needed":
        footer_parts.append("Review the draft and send or edit it manually in Front.")
    if email_summary:
        footer_parts.append(f"Email summary: {email_summary}")

    subject = "Dify support notification"
    if notification_type == "classify":
        subject = "Dify support: classification needed"
    elif notification_type == "security":
        subject = "Dify support: security notification"

    return await email_notify.notify_bobby_email(
        message,
        conversation_id=conversation_id,
        subject=subject,
        footer="\n\n".join(footer_parts),
    )


async def notify_yongle(message: str, conversation_id: str = "") -> bool:
    return await email_notify.notify_yongle_email(message, conversation_id=conversation_id)


async def notify_limin(message: str, conversation_id: str = "") -> bool:
    return await email_notify.notify_limin_email(message, conversation_id=conversation_id)


async def notify_sybil(message: str) -> bool:
    return await email_notify.notify_sybil_email(message)
