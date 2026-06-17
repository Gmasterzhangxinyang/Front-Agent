import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from config import settings

logger = logging.getLogger(__name__)


def _split_emails(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def _front_url(conversation_id: str) -> str:
    if not conversation_id:
        return ""
    return f"{settings.front_app_base_url.rstrip('/')}/{conversation_id}"


def _build_body(message: str, conversation_id: str = "", footer: str = "") -> str:
    parts = [message.strip()]
    if conversation_id:
        parts.extend(["", f"Conversation ID: {conversation_id}"])
        parts.append(f"Front: {_front_url(conversation_id)}")
    if footer:
        parts.extend(["", footer.strip()])
    return "\n".join(parts).strip() + "\n"


def _send_sync(to_emails: list[str], subject: str, body: str) -> bool:
    if not settings.smtp_host:
        logger.warning("SMTP host is not configured; email notification skipped")
        return False
    if not settings.notification_email_from:
        logger.warning("notification_email_from is not configured; email notification skipped")
        return False
    if not to_emails:
        logger.warning("No notification email recipients configured; email notification skipped")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Dify Support Agent", settings.notification_email_from))
    msg["To"] = ", ".join(to_emails)
    msg.set_content(body)

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        return True
    except Exception as exc:
        logger.error("Email notification failed: %s", exc, exc_info=True)
        return False


async def send_email(to: str, subject: str, message: str, conversation_id: str = "", footer: str = "") -> bool:
    body = _build_body(message, conversation_id=conversation_id, footer=footer)
    return await asyncio.to_thread(_send_sync, _split_emails(to), subject, body)


async def notify_bobby_email(message: str, conversation_id: str = "", subject: str = "Dify support notification", footer: str = "") -> bool:
    return await send_email(settings.notification_email_bobby, subject, message, conversation_id, footer)


async def notify_limin_email(message: str, conversation_id: str = "") -> bool:
    return await send_email(settings.notification_email_limin, "Dify account notification", message, conversation_id)


async def notify_sybil_email(message: str, conversation_id: str = "") -> bool:
    return await send_email(settings.notification_email_sybil, "Dify education notification", message, conversation_id)


async def notify_yongle_email(message: str, conversation_id: str = "") -> bool:
    return await send_email(settings.notification_email_yongle, "Dify security notification", message, conversation_id)
