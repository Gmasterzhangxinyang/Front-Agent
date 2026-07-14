import argparse
import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from config import settings
from database import AsyncSessionLocal, init_db
from models import SybilNotification
from tools import feishu

logger = logging.getLogger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
PENDING = "pending"
SENDING = "sending"
SENT = "sent"
SENDING_LEASE_PREFIX = "digest-lease:"
SENDING_LEASE_SECONDS = 30 * 60


def _new_sending_lease(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    expires_at = int(current.timestamp()) + SENDING_LEASE_SECONDS
    return f"{SENDING_LEASE_PREFIX}{expires_at}:{uuid4().hex}"


def _sending_lease_expired(
    marker: str | None,
    now: datetime | None = None,
) -> bool:
    if not marker or not marker.startswith(SENDING_LEASE_PREFIX):
        return True
    try:
        expires_text, token = marker.removeprefix(SENDING_LEASE_PREFIX).split(
            ":",
            1,
        )
        expires_at = int(expires_text)
        if len(token) != 32 or any(
            character not in "0123456789abcdef" for character in token
        ):
            return True
    except (IndexError, ValueError):
        return True
    current = now or datetime.now(timezone.utc)
    return expires_at <= int(current.timestamp())


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
    claim_marker = _new_sending_lease()
    claimed_ids = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SybilNotification.id, SybilNotification.error).where(
                SybilNotification.status == SENDING
            )
        )
        for notification_id, lease_marker in result.all():
            if not _sending_lease_expired(lease_marker):
                continue
            await db.execute(
                update(SybilNotification)
                .where(
                    SybilNotification.id == notification_id,
                    SybilNotification.status == SENDING,
                    SybilNotification.error == lease_marker,
                )
                .values(
                    status=PENDING,
                    error="Previous digest send lease expired",
                )
            )

        result = await db.execute(
            select(SybilNotification.id)
            .where(SybilNotification.status == PENDING)
            .order_by(SybilNotification.created_at.asc(), SybilNotification.id.asc())
            .limit(limit)
        )
        candidate_ids = list(result.scalars().all())
        for notification_id in candidate_ids:
            claimed = await db.execute(
                update(SybilNotification)
                .where(
                    SybilNotification.id == notification_id,
                    SybilNotification.status == PENDING,
                )
                .values(status=SENDING, error=claim_marker)
            )
            if claimed.rowcount == 1:
                claimed_ids.append(notification_id)
        await db.commit()

        if claimed_ids:
            result = await db.execute(
                select(SybilNotification)
                .where(
                    SybilNotification.id.in_(claimed_ids),
                    SybilNotification.status == SENDING,
                    SybilNotification.error == claim_marker,
                )
                .order_by(
                    SybilNotification.created_at.asc(),
                    SybilNotification.id.asc(),
                )
            )
            notifications = list(result.scalars().all())
        else:
            notifications = []

    if not notifications:
        logger.info("No pending Sybil notifications to send")
        return {"ok": True, "sent_count": 0}

    text = build_sybil_digest_message(notifications)
    try:
        ok = await feishu.send_sybil_group_text(text)
    except Exception:
        logger.exception("Failed to send claimed Sybil digest")
        ok = False

    async with AsyncSessionLocal() as db:
        if not ok:
            restored = await db.execute(
                update(SybilNotification)
                .where(
                    SybilNotification.id.in_(claimed_ids),
                    SybilNotification.status == SENDING,
                    SybilNotification.error == claim_marker,
                )
                .values(
                    status=PENDING,
                    error="Feishu digest send failed",
                )
            )
            await db.commit()
            return {
                "ok": False,
                "sent_count": 0,
                "pending_count": restored.rowcount,
            }

        sent_at = datetime.utcnow()
        sent = await db.execute(
            update(SybilNotification)
            .where(
                SybilNotification.id.in_(claimed_ids),
                SybilNotification.status == SENDING,
                SybilNotification.error == claim_marker,
            )
            .values(
                status=SENT,
                sent_at=sent_at,
                error="",
            )
        )
        await db.commit()
        logger.info("Sent Sybil digest with %s notifications", sent.rowcount)
        return {"ok": True, "sent_count": sent.rowcount}


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Send pending Sybil Feishu digest immediately.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    await init_db()
    result = await send_pending_sybil_digest(limit=args.limit)
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
