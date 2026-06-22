import argparse
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal, init_db
from models import SybilNotification
from tools import feishu

logger = logging.getLogger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
PENDING = "pending"
SENT = "sent"


def _clip(value: str, limit: int = 700) -> str:
    text = " ".join((value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "...[truncated]"


def _front_url(conversation_id: str) -> str:
    if not conversation_id:
        return ""
    return f"{settings.front_app_base_url.rstrip(chr(47))}/{conversation_id}"


def _format_created_at(value: datetime | None) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        return value.strftime("%Y-%m-%d %H:%M")
    return value.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")


def build_sybil_digest_message(notifications: list[SybilNotification]) -> str:
    now = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{feishu.sybil_mention()} Sybil handoff digest ({now} China time)",
        f"Total pending: {len(notifications)}",
        "",
    ]

    for idx, item in enumerate(notifications, start=1):
        handoff_type = (item.handoff_type or "sybil_handoff").strip()
        created_at = _format_created_at(item.created_at)
        message = _clip(item.message)
        lines.append(f"{idx}. [{handoff_type}] {message}")
        if item.linear_url and item.linear_url not in message:
            lines.append(f"   Linear: {item.linear_url}")
        if item.conversation_id:
            lines.append(f"   Front: {_front_url(item.conversation_id)}")
        if item.cc_email:
            lines.append(f"   CC: {item.cc_email}")
        if created_at:
            lines.append(f"   Queued: {created_at}")
        lines.append("")

    return chr(10).join(lines).strip()


async def queue_sybil_notification(
    message: str,
    conversation_id: str,
    cc_email: str = "",
    handoff_type: str = "",
    linear_url: str = "",
) -> bool:
    if not conversation_id:
        logger.warning("Cannot queue Sybil notification without conversation_id")
        return False

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SybilNotification).where(
                    SybilNotification.conversation_id == conversation_id,
                    SybilNotification.status == PENDING,
                )
            )
            notification = result.scalars().first()
            if notification is None:
                notification = SybilNotification(conversation_id=conversation_id, message=message)
                db.add(notification)

            notification.message = message
            notification.cc_email = cc_email or ""
            notification.handoff_type = handoff_type or ""
            notification.linear_url = linear_url or ""
            notification.error = ""
            await db.commit()
        return True
    except Exception:
        logger.exception("Failed to queue Sybil notification")
        return False


async def send_pending_sybil_digest(limit: int = 100) -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SybilNotification)
            .where(SybilNotification.status == PENDING)
            .order_by(SybilNotification.created_at.asc(), SybilNotification.id.asc())
            .limit(limit)
        )
        notifications = list(result.scalars().all())
        if not notifications:
            logger.info("No pending Sybil notifications to send")
            return {"ok": True, "sent_count": 0}

        text = build_sybil_digest_message(notifications)
        ok = await feishu.send_sybil_group_text(text)
        if not ok:
            for item in notifications:
                item.error = "Feishu digest send failed"
            await db.commit()
            return {"ok": False, "sent_count": 0, "pending_count": len(notifications)}

        sent_at = datetime.utcnow()
        for item in notifications:
            item.status = SENT
            item.sent_at = sent_at
            item.error = ""
        await db.commit()
        logger.info("Sent Sybil digest with %s notifications", len(notifications))
        return {"ok": True, "sent_count": len(notifications)}


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Send pending Sybil Feishu digest immediately.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    await init_db()
    result = await send_pending_sybil_digest(limit=args.limit)
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
