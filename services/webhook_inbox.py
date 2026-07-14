import hashlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.sqlite import insert

from database import AsyncSessionLocal
from models import WebhookInbox


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
