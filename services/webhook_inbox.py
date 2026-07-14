import hashlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.sqlite import insert

from database import AsyncSessionLocal
from models import WebhookInbox


MAX_ATTEMPTS = 6
RETRY_DELAYS_MINUTES = (1, 5, 15, 60, 180)
LEASE_DURATION = timedelta(minutes=15)
ERROR_SUMMARY_LIMIT = 500


@dataclass(frozen=True)
class InboxSnapshot:
    event_id: str
    conversation_id: str
    payload: dict
    status: str
    attempts: int
    available_at: datetime
    lease_token: str | None
    lease_expires_at: datetime | None
    last_error: str


def derive_event_id(payload: dict, raw_body: bytes) -> str:
    for key in ("id", "event_id"):
        if payload.get(key) is not None:
            return str(payload[key])
    return f"sha256:{hashlib.sha256(raw_body).hexdigest()}"


def _snapshot(row: WebhookInbox) -> InboxSnapshot:
    return InboxSnapshot(
        event_id=row.event_id,
        conversation_id=row.conversation_id,
        payload=deepcopy(row.payload),
        status=row.status,
        attempts=row.attempts,
        available_at=row.available_at,
        lease_token=row.lease_token,
        lease_expires_at=row.lease_expires_at,
        last_error=row.last_error,
    )


async def enqueue_webhook(
    event_id: str,
    conversation_id: str,
    payload: dict,
    *,
    now: datetime | None = None,
) -> InboxSnapshot:
    timestamp = now or datetime.utcnow()
    statement = (
        insert(WebhookInbox)
        .values(
            event_id=event_id,
            conversation_id=conversation_id,
            payload=payload,
            status="pending",
            attempts=0,
            available_at=timestamp,
            lease_token=None,
            lease_expires_at=None,
            last_error="",
            created_at=timestamp,
            updated_at=timestamp,
            processed_at=None,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )

    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()
        row = await session.get(WebhookInbox, event_id)

    if row is None:
        raise RuntimeError(f"webhook inbox row missing after enqueue: {event_id}")
    return _snapshot(row)


def _claimable(now: datetime):
    return or_(
        and_(
            WebhookInbox.status.in_(("pending", "retry")),
            WebhookInbox.available_at <= now,
        ),
        and_(
            WebhookInbox.status == "processing",
            WebhookInbox.lease_expires_at.is_not(None),
            WebhookInbox.lease_expires_at <= now,
        ),
    )


async def get_webhook(event_id: str) -> InboxSnapshot | None:
    async with AsyncSessionLocal() as session:
        row = await session.get(WebhookInbox, event_id)
        return _snapshot(row) if row is not None else None


async def claim_webhook(
    event_id: str,
    *,
    now: datetime | None = None,
) -> InboxSnapshot | None:
    timestamp = now or datetime.utcnow()
    lease_token = uuid4().hex
    statement = (
        update(WebhookInbox)
        .where(
            WebhookInbox.event_id == event_id,
            _claimable(timestamp),
        )
        .values(
            status="processing",
            attempts=WebhookInbox.attempts + 1,
            lease_token=lease_token,
            lease_expires_at=timestamp + LEASE_DURATION,
            updated_at=timestamp,
        )
        .execution_options(synchronize_session=False)
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        await session.commit()
        if result.rowcount != 1:
            return None
        row = await session.get(
            WebhookInbox,
            event_id,
            populate_existing=True,
        )
        return _snapshot(row) if row is not None else None


async def list_due_event_ids(
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> list[str]:
    if limit <= 0:
        return []

    timestamp = now or datetime.utcnow()
    statement = (
        select(WebhookInbox.event_id)
        .where(_claimable(timestamp))
        .order_by(WebhookInbox.available_at, WebhookInbox.created_at)
        .limit(limit)
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return list(result.scalars().all())


async def complete_webhook(
    event_id: str,
    lease_token: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    if not lease_token:
        return False

    timestamp = now or datetime.utcnow()
    statement = (
        update(WebhookInbox)
        .where(
            WebhookInbox.event_id == event_id,
            WebhookInbox.status == "processing",
            WebhookInbox.lease_token == lease_token,
        )
        .values(
            status="processed",
            payload={},
            lease_token=None,
            lease_expires_at=None,
            last_error="",
            processed_at=timestamp,
            updated_at=timestamp,
        )
        .execution_options(synchronize_session=False)
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        await session.commit()
        return result.rowcount == 1


async def fail_webhook(
    event_id: str,
    lease_token: str | None,
    error,
    *,
    now: datetime | None = None,
) -> InboxSnapshot | None:
    if not lease_token:
        return None

    timestamp = now or datetime.utcnow()
    ownership = (
        WebhookInbox.event_id == event_id,
        WebhookInbox.status == "processing",
        WebhookInbox.lease_token == lease_token,
    )

    async with AsyncSessionLocal() as session:
        attempts_result = await session.execute(
            select(WebhookInbox.attempts).where(*ownership)
        )
        attempts = attempts_result.scalar_one_or_none()
        if attempts is None:
            return None

        values = {
            "status": "dead_letter",
            "lease_token": None,
            "lease_expires_at": None,
            "last_error": str(error)[:ERROR_SUMMARY_LIMIT],
            "updated_at": timestamp,
        }
        if attempts < MAX_ATTEMPTS:
            values["status"] = "retry"
            values["available_at"] = timestamp + timedelta(
                minutes=RETRY_DELAYS_MINUTES[attempts - 1]
            )

        statement = (
            update(WebhookInbox)
            .where(*ownership)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(statement)
        await session.commit()
        if result.rowcount != 1:
            return None
        row = await session.get(
            WebhookInbox,
            event_id,
            populate_existing=True,
        )
        return _snapshot(row) if row is not None else None
