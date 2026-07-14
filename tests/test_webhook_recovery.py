import asyncio
import hashlib
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import WebhookInbox
import services.webhook_inbox as webhook_inbox
from services.webhook_inbox import derive_event_id


@asynccontextmanager
async def _isolated_inbox():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        with patch.object(webhook_inbox, "AsyncSessionLocal", session_factory):
            yield session_factory
    finally:
        await engine.dispose()


async def _store_event(
    session_factory,
    event_id,
    *,
    available_at,
    created_at=None,
    status="pending",
    attempts=0,
    lease_token=None,
    lease_expires_at=None,
    last_error="",
    payload=None,
):
    timestamp = created_at or available_at
    async with session_factory() as session:
        session.add(
            WebhookInbox(
                event_id=event_id,
                conversation_id=f"cnv_{event_id}",
                payload=payload or {"id": event_id},
                status=status,
                attempts=attempts,
                available_at=available_at,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                last_error=last_error,
                created_at=timestamp,
                updated_at=timestamp,
                processed_at=None,
            )
        )
        await session.commit()


def test_derive_event_id_prefers_front_id_and_hashes_missing_id():
    raw_body = b'{"type":"message","target":{"data":{"id":null}}}'

    assert derive_event_id(
        {"id": "evt_front", "event_id": "evt_other"},
        raw_body,
    ) == "evt_front"
    assert derive_event_id({"event_id": "evt_legacy"}, raw_body) == "evt_legacy"
    assert derive_event_id({}, raw_body) == (
        f"sha256:{hashlib.sha256(raw_body).hexdigest()}"
    )


def test_enqueue_is_durable_and_duplicate_safe():
    async def run_case():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime(2026, 7, 14, 9, 30, 0)
        original_payload = {"id": "evt_enqueue", "type": "message"}

        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            with patch.object(
                webhook_inbox,
                "AsyncSessionLocal",
                session_factory,
            ):
                first = await webhook_inbox.enqueue_webhook(
                    "evt_enqueue",
                    "cnv_enqueue",
                    original_payload,
                    now=now,
                )
                duplicate = await webhook_inbox.enqueue_webhook(
                    "evt_enqueue",
                    "cnv_changed",
                    {"id": "evt_enqueue", "type": "changed"},
                    now=now + timedelta(minutes=1),
                )

            assert first.event_id == "evt_enqueue"
            assert first.conversation_id == "cnv_enqueue"
            assert first.payload == original_payload
            assert first.status == "pending"
            assert first.attempts == 0
            assert first.available_at == now
            assert duplicate == first

            async with session_factory() as session:
                stored = await session.get(WebhookInbox, "evt_enqueue")

            assert stored is not None
            assert stored.conversation_id == "cnv_enqueue"
            assert stored.payload == original_payload
            assert stored.available_at == now
        finally:
            await engine.dispose()

    asyncio.run(run_case())


def test_only_due_pending_and_retry_records_can_be_claimed():
    async def run_case():
        now = datetime(2026, 7, 14, 10, 0, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(
                session_factory, "evt_pending_due", available_at=now
            )
            await _store_event(
                session_factory,
                "evt_pending_future",
                available_at=now + timedelta(seconds=1),
            )
            await _store_event(
                session_factory,
                "evt_retry_due",
                available_at=now - timedelta(minutes=1),
                status="retry",
                attempts=1,
            )
            await _store_event(
                session_factory,
                "evt_retry_future",
                available_at=now + timedelta(minutes=1),
                status="retry",
                attempts=1,
            )
            await _store_event(
                session_factory,
                "evt_retry_exhausted",
                available_at=now - timedelta(minutes=1),
                status="retry",
                attempts=webhook_inbox.MAX_ATTEMPTS,
            )
            await _store_event(
                session_factory,
                "evt_processed",
                available_at=now - timedelta(hours=1),
                status="processed",
                attempts=1,
            )

            assert await webhook_inbox.list_due_event_ids(now=now) == [
                "evt_retry_due",
                "evt_pending_due",
            ]
            assert await webhook_inbox.get_webhook("evt_pending_due") is not None
            assert await webhook_inbox.get_webhook("evt_missing") is None
            assert (
                await webhook_inbox.claim_webhook("evt_pending_due", now=now)
                is not None
            )
            assert (
                await webhook_inbox.claim_webhook("evt_retry_due", now=now)
                is not None
            )
            assert (
                await webhook_inbox.claim_webhook("evt_pending_future", now=now)
                is None
            )
            assert (
                await webhook_inbox.claim_webhook("evt_retry_future", now=now)
                is None
            )
            assert (
                await webhook_inbox.claim_webhook("evt_retry_exhausted", now=now)
                is None
            )
            assert (
                await webhook_inbox.claim_webhook("evt_processed", now=now)
                is None
            )

    asyncio.run(run_case())


def test_first_claim_creates_an_active_fifteen_minute_lease():
    async def run_case():
        now = datetime(2026, 7, 14, 10, 30, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(session_factory, "evt_claim", available_at=now)

            claimed = await webhook_inbox.claim_webhook("evt_claim", now=now)

            assert claimed is not None
            assert claimed.status == "processing"
            assert claimed.attempts == 1
            assert claimed.lease_token
            assert claimed.lease_expires_at == now + timedelta(minutes=15)
            assert await webhook_inbox.claim_webhook("evt_claim", now=now) is None
            assert await webhook_inbox.list_due_event_ids(now=now) == []

    asyncio.run(run_case())


def test_expired_lease_can_be_reclaimed_with_a_new_token():
    async def run_case():
        now = datetime(2026, 7, 14, 11, 0, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(session_factory, "evt_expired", available_at=now)
            first = await webhook_inbox.claim_webhook("evt_expired", now=now)
            assert first is not None

            recovery_time = now + timedelta(minutes=15)
            assert await webhook_inbox.list_due_event_ids(now=recovery_time) == [
                "evt_expired"
            ]
            recovered = await webhook_inbox.claim_webhook(
                "evt_expired",
                now=recovery_time,
            )

            assert recovered is not None
            assert recovered.status == "processing"
            assert recovered.attempts == 2
            assert recovered.lease_token != first.lease_token
            assert recovered.lease_expires_at == recovery_time + timedelta(minutes=15)

    asyncio.run(run_case())


def test_stale_token_cannot_complete_a_newer_claim():
    async def run_case():
        now = datetime(2026, 7, 14, 11, 30, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(session_factory, "evt_stale_complete", available_at=now)
            first = await webhook_inbox.claim_webhook("evt_stale_complete", now=now)
            assert first is not None
            recovered = await webhook_inbox.claim_webhook(
                "evt_stale_complete", now=now + timedelta(minutes=15)
            )
            assert recovered is not None

            assert not await webhook_inbox.complete_webhook(
                "evt_stale_complete",
                first.lease_token,
                now=now + timedelta(minutes=16),
            )
            stored = await webhook_inbox.get_webhook("evt_stale_complete")
            assert stored is not None
            assert stored.status == "processing"
            assert stored.lease_token == recovered.lease_token
            assert stored.attempts == 2

    asyncio.run(run_case())


def test_stale_token_cannot_fail_a_newer_claim():
    async def run_case():
        now = datetime(2026, 7, 14, 12, 0, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(session_factory, "evt_stale_fail", available_at=now)
            first = await webhook_inbox.claim_webhook("evt_stale_fail", now=now)
            assert first is not None
            recovered = await webhook_inbox.claim_webhook(
                "evt_stale_fail", now=now + timedelta(minutes=15)
            )
            assert recovered is not None

            assert (
                await webhook_inbox.fail_webhook(
                    "evt_stale_fail",
                    first.lease_token,
                    RuntimeError("stale worker"),
                    now=now + timedelta(minutes=16),
                )
                is None
            )
            stored = await webhook_inbox.get_webhook("evt_stale_fail")
            assert stored is not None
            assert stored.status == "processing"
            assert stored.lease_token == recovered.lease_token
            assert stored.last_error == ""
            assert stored.attempts == 2

    asyncio.run(run_case())


def test_complete_clears_sensitive_state_and_removes_due_work():
    async def run_case():
        now = datetime(2026, 7, 14, 12, 30, 0)
        completed_at = now + timedelta(minutes=2)
        async with _isolated_inbox() as session_factory:
            await _store_event(
                session_factory,
                "evt_complete",
                available_at=now,
                payload={"id": "evt_complete", "secret": "discard me"},
                last_error="old failure",
            )
            claim = await webhook_inbox.claim_webhook("evt_complete", now=now)
            assert claim is not None

            assert not await webhook_inbox.complete_webhook(
                "evt_complete",
                None,
                now=completed_at,
            )
            assert await webhook_inbox.complete_webhook(
                "evt_complete",
                claim.lease_token,
                now=completed_at,
            )

            async with session_factory() as session:
                stored = await session.get(WebhookInbox, "evt_complete")
            assert stored is not None
            assert stored.status == "processed"
            assert stored.payload == {}
            assert stored.lease_token is None
            assert stored.lease_expires_at is None
            assert stored.last_error == ""
            assert stored.processed_at == completed_at
            assert stored.updated_at == completed_at
            assert await webhook_inbox.list_due_event_ids(
                now=completed_at + timedelta(days=1)
            ) == []

    asyncio.run(run_case())


def test_retry_delays_follow_the_exact_backoff_sequence():
    async def run_case():
        now = datetime(2026, 7, 14, 13, 0, 0)
        expected_delays = (1, 5, 15, 60, 180)
        async with _isolated_inbox() as session_factory:
            await _store_event(session_factory, "evt_backoff", available_at=now)
            claim_time = now

            for attempt, delay_minutes in enumerate(expected_delays, start=1):
                claimed = await webhook_inbox.claim_webhook(
                    "evt_backoff",
                    now=claim_time,
                )
                assert claimed is not None
                assert claimed.attempts == attempt

                failed_at = claim_time + timedelta(seconds=30)
                failed = await webhook_inbox.fail_webhook(
                    "evt_backoff",
                    claimed.lease_token,
                    f"attempt {attempt}",
                    now=failed_at,
                )
                assert failed is not None
                assert failed.status == "retry"
                assert failed.available_at == failed_at + timedelta(
                    minutes=delay_minutes
                )
                assert failed.lease_token is None
                assert failed.lease_expires_at is None
                claim_time = failed.available_at

    asyncio.run(run_case())


def test_sixth_failure_dead_letters_and_retains_bounded_diagnostics():
    async def run_case():
        now = datetime(2026, 7, 14, 14, 0, 0)
        payload = {"id": "evt_dead", "body": "retain me"}
        token = "sixth-attempt-token"
        async with _isolated_inbox() as session_factory:
            await _store_event(
                session_factory,
                "evt_dead",
                available_at=now - timedelta(hours=1),
                status="processing",
                attempts=6,
                lease_token=token,
                lease_expires_at=now + timedelta(minutes=15),
                payload=payload,
            )

            assert (
                await webhook_inbox.fail_webhook(
                    "evt_dead",
                    None,
                    "ignored",
                    now=now,
                )
                is None
            )
            failed = await webhook_inbox.fail_webhook(
                "evt_dead",
                token,
                "x" * 600,
                now=now,
            )

            assert failed is not None
            assert failed.status == "dead_letter"
            assert failed.payload == payload
            assert failed.last_error == "x" * 500
            assert failed.lease_token is None
            assert failed.lease_expires_at is None
            assert await webhook_inbox.list_due_event_ids(
                now=now + timedelta(days=365)
            ) == []

    asyncio.run(run_case())


def test_due_list_respects_limit_and_orders_by_availability_then_creation():
    async def run_case():
        now = datetime(2026, 7, 14, 15, 0, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(
                session_factory,
                "evt_second",
                available_at=now - timedelta(minutes=1),
                created_at=now - timedelta(hours=2),
            )
            await _store_event(
                session_factory,
                "evt_third",
                available_at=now - timedelta(minutes=1),
                created_at=now - timedelta(hours=1),
            )
            await _store_event(
                session_factory,
                "evt_first",
                available_at=now - timedelta(minutes=2),
                created_at=now,
            )
            await _store_event(
                session_factory,
                "evt_fourth",
                available_at=now,
                created_at=now - timedelta(hours=3),
            )

            assert await webhook_inbox.list_due_event_ids(
                now=now,
                limit=3,
            ) == ["evt_first", "evt_second", "evt_third"]

    asyncio.run(run_case())


def test_abandoned_sixth_claim_terminalizes_instead_of_attempting_seven():
    async def run_case():
        now = datetime(2026, 7, 14, 16, 0, 0)
        payload = {"id": "evt_abandoned", "body": "retain me"}
        async with _isolated_inbox() as session_factory:
            await _store_event(
                session_factory,
                "evt_abandoned",
                available_at=now,
                payload=payload,
            )
            claim_time = now

            for expected_attempts in range(1, 7):
                claimed = await webhook_inbox.claim_webhook(
                    "evt_abandoned",
                    now=claim_time,
                )
                assert claimed is not None
                assert claimed.attempts == expected_attempts
                claim_time = claimed.lease_expires_at

            assert await webhook_inbox.list_due_event_ids(now=claim_time) == [
                "evt_abandoned"
            ]
            assert (
                await webhook_inbox.claim_webhook(
                    "evt_abandoned",
                    now=claim_time,
                )
                is None
            )

            stored = await webhook_inbox.get_webhook("evt_abandoned")
            assert stored is not None
            assert stored.status == "dead_letter"
            assert stored.attempts == 6
            assert stored.payload == payload
            assert stored.lease_token is None
            assert stored.lease_expires_at is None
            assert stored.last_error
            assert len(stored.last_error) <= webhook_inbox.ERROR_SUMMARY_LIMIT
            assert await webhook_inbox.list_due_event_ids(
                now=claim_time + timedelta(days=1)
            ) == []

    asyncio.run(run_case())


def test_due_list_uses_event_id_to_break_exact_timestamp_ties():
    async def run_case():
        now = datetime(2026, 7, 14, 17, 0, 0)
        async with _isolated_inbox() as session_factory:
            await _store_event(
                session_factory,
                "evt_zeta",
                available_at=now,
                created_at=now,
            )
            await _store_event(
                session_factory,
                "evt_alpha",
                available_at=now,
                created_at=now,
            )

            assert await webhook_inbox.list_due_event_ids(now=now) == [
                "evt_alpha",
                "evt_zeta",
            ]

    asyncio.run(run_case())


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("webhook recovery tests passed")
