# Durable Front Webhook Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every authenticated conversation webhook before processing and automatically retry temporary failures without changing normal immediate handling.

**Architecture:** Add a dedicated SQLite `webhook_inbox` state machine behind a focused service module. The HTTP path enqueues and immediately claims an event, while APScheduler reuses the same claim-and-process entry point for due or abandoned events; existing `webhook_events`, action idempotency, semaphore, and conversation locks remain authoritative.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy async, SQLite/aiosqlite, APScheduler, standalone offline test scripts.

---

## File Structure

- Create `services/webhook_inbox.py`: stable IDs, enqueue, atomic claims, leases, retry transitions, terminal cleanup, and due-event queries.
- Create `tests/test_webhook_recovery.py`: isolated SQLite state-machine tests plus webhook and scheduler integration tests.
- Modify `models.py`: add only the `WebhookInbox` ORM model; do not change existing table schemas.
- Modify `webhooks/front_webhook.py`: persist before processing and expose the shared immediate/background processing entry point.
- Modify `tasks/scheduler.py`: add the one-minute recovery job while preserving the existing uncommitted draft-adoption refresh code.
- Modify `README.md`, `docs/runtime-boundaries.md`, and `CLAUDE.md`: document recovery semantics and verification.
- Modify `record.md`: append the implementation entry required by repository guidance.

## Working Tree Constraints

- Do not modify or stage `routes/ops.py`.
- Do not modify or stage `tests/test_routing.py`.
- `tasks/scheduler.py` already contains uncommitted draft-adoption work. Keep it intact and stage only the webhook-retry function and scheduler registration hunks.
- Do not deploy or restart the production process as part of implementation verification. Deployment requires a separate explicit step after the branch is verified.

### Task 1: Inbox Model, Stable IDs, and Durable Enqueue

**Files:**
- Create: `tests/test_webhook_recovery.py`
- Modify: `models.py`
- Create: `services/webhook_inbox.py`

- [ ] **Step 1: Write failing model and enqueue tests**

Create `tests/test_webhook_recovery.py` with an isolated database harness and these first tests:

```python
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import WebhookInbox
import services.webhook_inbox as inbox_module
from services.webhook_inbox import derive_event_id, enqueue_webhook


async def _with_database(case):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        with patch.object(inbox_module, "AsyncSessionLocal", sessions):
            await case(sessions)
    finally:
        await engine.dispose()


def test_derive_event_id_prefers_front_id_and_hashes_missing_id():
    body = b'{"conversation_id":"cnv_hash"}'
    assert derive_event_id({"id": "evt_front"}, body) == "evt_front"
    assert derive_event_id({"event_id": "evt_legacy"}, body) == "evt_legacy"
    assert derive_event_id({}, body) == f"sha256:{hashlib.sha256(body).hexdigest()}"


def test_enqueue_is_durable_and_duplicate_safe():
    async def case(sessions):
        now = datetime(2026, 7, 14, 10, 0, 0)
        first = await enqueue_webhook(
            "evt_enqueue",
            "cnv_enqueue",
            {"id": "evt_enqueue", "body": "original"},
            now=now,
        )
        duplicate = await enqueue_webhook(
            "evt_enqueue",
            "cnv_changed",
            {"id": "evt_enqueue", "body": "replacement"},
            now=now + timedelta(minutes=1),
        )

        assert first.status == "pending"
        assert first.attempts == 0
        assert duplicate.conversation_id == "cnv_enqueue"
        assert duplicate.payload["body"] == "original"

        async with sessions() as db:
            stored = await db.get(WebhookInbox, "evt_enqueue")
            assert stored is not None
            assert stored.available_at == now

    asyncio.run(_with_database(case))
```

Keep the file's runner at the end from the first commit:

```python
def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("webhook recovery tests passed")
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Expected: FAIL because `WebhookInbox` and `services.webhook_inbox` do not exist.

- [ ] **Step 3: Add the ORM model**

In `models.py`, add this model immediately after `WebhookEvent`:

```python
class WebhookInbox(Base):
    __tablename__ = "webhook_inbox"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    lease_token: Mapped[str] = mapped_column(String, nullable=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    processed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: Implement stable ID and enqueue operations**

Create `services/webhook_inbox.py` with the initial service boundary:

```python
import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

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
    front_id = payload.get("id") or payload.get("event_id")
    if front_id:
        return str(front_id)
    return f"sha256:{hashlib.sha256(raw_body).hexdigest()}"


def _snapshot(row: WebhookInbox) -> InboxSnapshot:
    return InboxSnapshot(
        event_id=row.event_id,
        conversation_id=row.conversation_id,
        payload=dict(row.payload or {}),
        status=row.status,
        attempts=row.attempts,
        available_at=row.available_at,
        lease_token=row.lease_token,
        lease_expires_at=row.lease_expires_at,
        last_error=row.last_error or "",
    )


async def enqueue_webhook(
    event_id: str,
    conversation_id: str,
    payload: dict,
    *,
    now: datetime | None = None,
) -> InboxSnapshot:
    now = now or datetime.utcnow()
    statement = (
        sqlite_insert(WebhookInbox)
        .values(
            event_id=event_id,
            conversation_id=conversation_id,
            payload=payload,
            status="pending",
            attempts=0,
            available_at=now,
            last_error="",
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
    async with AsyncSessionLocal() as db:
        await db.execute(statement)
        await db.commit()
        row = await db.get(WebhookInbox, event_id)
        if row is None:
            raise RuntimeError(f"webhook inbox insert missing after commit: {event_id}")
        return _snapshot(row)
```

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Expected: `webhook recovery tests passed`.

- [ ] **Step 6: Commit the model and enqueue boundary**

```bash
git add models.py services/webhook_inbox.py tests/test_webhook_recovery.py
git commit -m "feat: persist front webhook inbox events"
```

### Task 2: Atomic Claims, Leases, Retry Backoff, and Terminal Cleanup

**Files:**
- Modify: `services/webhook_inbox.py`
- Modify: `tests/test_webhook_recovery.py`

- [ ] **Step 1: Add failing state-machine tests**

Extend the service imports in `tests/test_webhook_recovery.py`:

```python
from services.webhook_inbox import (
    MAX_ATTEMPTS,
    claim_webhook,
    complete_webhook,
    derive_event_id,
    enqueue_webhook,
    fail_webhook,
    list_due_event_ids,
)
```

Add tests that exercise active leases, stale claims, cleanup, backoff, and dead letters:

```python
def test_claim_is_exclusive_and_expired_lease_is_recoverable():
    async def case(_sessions):
        now = datetime(2026, 7, 14, 10, 0, 0)
        await enqueue_webhook("evt_claim", "cnv_claim", {"body": "x"}, now=now)

        first = await claim_webhook("evt_claim", now=now)
        assert first is not None
        assert first.status == "processing"
        assert first.attempts == 1
        assert await claim_webhook("evt_claim", now=now + timedelta(minutes=1)) is None

        recovered = await claim_webhook("evt_claim", now=now + timedelta(minutes=16))
        assert recovered is not None
        assert recovered.attempts == 2
        assert recovered.lease_token != first.lease_token

        assert not await complete_webhook(
            first.event_id,
            first.lease_token,
            now=now + timedelta(minutes=16),
        )

    asyncio.run(_with_database(case))


def test_complete_clears_payload_and_removes_event_from_due_work():
    async def case(sessions):
        now = datetime(2026, 7, 14, 10, 0, 0)
        await enqueue_webhook("evt_complete", "cnv_complete", {"secret": "mail"}, now=now)
        claim = await claim_webhook("evt_complete", now=now)
        assert claim is not None
        assert await complete_webhook(claim.event_id, claim.lease_token, now=now)

        assert await list_due_event_ids(now=now + timedelta(days=1)) == []
        async with sessions() as db:
            row = await db.get(WebhookInbox, "evt_complete")
            assert row.status == "processed"
            assert row.payload == {}
            assert row.processed_at == now

    asyncio.run(_with_database(case))


def test_retry_schedule_and_dead_letter_are_bounded():
    async def case(sessions):
        now = datetime(2026, 7, 14, 10, 0, 0)
        expected_delays = [1, 5, 15, 60, 180]
        await enqueue_webhook("evt_retry", "cnv_retry", {"body": "retry"}, now=now)

        current = now
        for attempt, delay in enumerate(expected_delays, start=1):
            claim = await claim_webhook("evt_retry", now=current)
            assert claim is not None
            assert claim.attempts == attempt
            outcome = await fail_webhook(
                claim.event_id,
                claim.lease_token,
                RuntimeError("temporary failure"),
                now=current,
            )
            assert outcome is not None
            assert outcome.status == "retry"
            assert outcome.available_at == current + timedelta(minutes=delay)
            current = outcome.available_at

        final_claim = await claim_webhook("evt_retry", now=current)
        assert final_claim is not None
        assert final_claim.attempts == MAX_ATTEMPTS
        outcome = await fail_webhook(
            final_claim.event_id,
            final_claim.lease_token,
            RuntimeError("permanent after retries"),
            now=current,
        )
        assert outcome is not None
        assert outcome.status == "dead_letter"
        assert await list_due_event_ids(now=current + timedelta(days=1)) == []

        async with sessions() as db:
            row = await db.get(WebhookInbox, "evt_retry")
            assert row.payload == {"body": "retry"}
            assert row.last_error == "permanent after retries"

    asyncio.run(_with_database(case))
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Expected: FAIL because claim, completion, due-query, and failure functions are missing.

- [ ] **Step 3: Implement the complete state machine**

Add these imports and constants to `services/webhook_inbox.py`:

```python
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update

MAX_ATTEMPTS = 6
RETRY_DELAYS_MINUTES = (1, 5, 15, 60, 180)
LEASE_DURATION = timedelta(minutes=15)
ERROR_SUMMARY_LIMIT = 500
```

Add the state operations:

```python
def _claimable(now: datetime):
    return or_(
        and_(
            WebhookInbox.status.in_(("pending", "retry")),
            WebhookInbox.available_at <= now,
        ),
        and_(
            WebhookInbox.status == "processing",
            WebhookInbox.lease_expires_at <= now,
        ),
    )


async def get_webhook(event_id: str) -> InboxSnapshot | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(WebhookInbox, event_id)
        return _snapshot(row) if row is not None else None


async def claim_webhook(
    event_id: str,
    *,
    now: datetime | None = None,
) -> InboxSnapshot | None:
    now = now or datetime.utcnow()
    token = uuid4().hex
    statement = (
        update(WebhookInbox)
        .where(WebhookInbox.event_id == event_id, _claimable(now))
        .values(
            status="processing",
            attempts=WebhookInbox.attempts + 1,
            lease_token=token,
            lease_expires_at=now + LEASE_DURATION,
            updated_at=now,
        )
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(statement)
        await db.commit()
        if result.rowcount != 1:
            return None
        row = await db.get(WebhookInbox, event_id)
        if row is None:
            raise RuntimeError(f"claimed webhook missing after commit: {event_id}")
        return _snapshot(row)


async def list_due_event_ids(
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> list[str]:
    now = now or datetime.utcnow()
    statement = (
        select(WebhookInbox.event_id)
        .where(_claimable(now))
        .order_by(WebhookInbox.available_at, WebhookInbox.created_at)
        .limit(limit)
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(statement)
        return list(result.scalars().all())


async def complete_webhook(
    event_id: str,
    lease_token: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    if not lease_token:
        return False
    now = now or datetime.utcnow()
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
            processed_at=now,
            updated_at=now,
        )
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(statement)
        await db.commit()
        return result.rowcount == 1


async def fail_webhook(
    event_id: str,
    lease_token: str | None,
    error: Exception,
    *,
    now: datetime | None = None,
) -> InboxSnapshot | None:
    if not lease_token:
        return None
    now = now or datetime.utcnow()
    summary = str(error)[:ERROR_SUMMARY_LIMIT]

    async with AsyncSessionLocal() as db:
        row = await db.get(WebhookInbox, event_id)
        if (
            row is None
            or row.status != "processing"
            or row.lease_token != lease_token
        ):
            return None

        if row.attempts >= MAX_ATTEMPTS:
            next_status = "dead_letter"
            available_at = now
        else:
            next_status = "retry"
            available_at = now + timedelta(
                minutes=RETRY_DELAYS_MINUTES[row.attempts - 1]
            )

        statement = (
            update(WebhookInbox)
            .where(
                WebhookInbox.event_id == event_id,
                WebhookInbox.status == "processing",
                WebhookInbox.lease_token == lease_token,
            )
            .values(
                status=next_status,
                available_at=available_at,
                lease_token=None,
                lease_expires_at=None,
                last_error=summary,
                updated_at=now,
            )
        )
        result = await db.execute(statement)
        await db.commit()
        if result.rowcount != 1:
            return None
        updated = await db.get(WebhookInbox, event_id, populate_existing=True)
        if updated is None:
            raise RuntimeError(f"failed webhook missing after commit: {event_id}")
        return _snapshot(updated)
```

- [ ] **Step 4: Run the state-machine tests and verify GREEN**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Expected: `webhook recovery tests passed`.

- [ ] **Step 5: Commit atomic recovery behavior**

```bash
git add services/webhook_inbox.py tests/test_webhook_recovery.py
git commit -m "feat: add leased webhook retry state machine"
```

### Task 3: Persist-Before-Process HTTP Integration

**Files:**
- Modify: `webhooks/front_webhook.py`
- Modify: `tests/test_webhook_recovery.py`
- Verify: `tests/test_runtime_boundaries.py`

- [ ] **Step 1: Add failing webhook integration tests**

Add imports:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

import webhooks.front_webhook as front_webhook_module
from services.webhook_inbox import InboxSnapshot
```

Add a minimal request fixture and integration tests:

```python
class _WebhookRequest:
    def __init__(self, payload):
        self._body = json.dumps(payload, separators=(",", ":")).encode()
        self.headers = {"X-Front-Signature": "valid"}

    async def body(self):
        return self._body


def _claim_snapshot(event_id="evt_flow", attempts=1):
    return InboxSnapshot(
        event_id=event_id,
        conversation_id="cnv_flow",
        payload={"id": event_id, "conversation_id": "cnv_flow"},
        status="processing",
        attempts=attempts,
        available_at=datetime(2026, 7, 14, 10, 0, 0),
        lease_token="lease_flow",
        lease_expires_at=datetime(2026, 7, 14, 10, 15, 0),
        last_error="",
    )


def test_route_persists_before_starting_processing():
    async def case():
        order = []

        async def enqueue(*_args, **_kwargs):
            order.append("persist")
            return SimpleNamespace(status="pending")

        async def process(event_id):
            order.append(f"process:{event_id}")
            return {"status": "ok"}

        payload = {"id": "evt_order", "conversation_id": "cnv_order"}
        with (
            patch.object(front_webhook_module, "verify_signature", return_value=True),
            patch.object(front_webhook_module, "enqueue_webhook", enqueue),
            patch.object(front_webhook_module, "process_inbox_event", process),
        ):
            result = await front_webhook_module.front_webhook(_WebhookRequest(payload))

        assert result == {"status": "ok"}
        assert order == ["persist", "process:evt_order"]

    asyncio.run(case())


def test_claimed_success_marks_inbox_processed():
    async def case():
        claim = _claim_snapshot()
        with (
            patch.object(front_webhook_module, "claim_webhook", AsyncMock(return_value=claim)),
            patch.object(
                front_webhook_module,
                "_process_front_webhook_event",
                AsyncMock(return_value={"status": "ok"}),
            ),
            patch.object(front_webhook_module, "complete_webhook", AsyncMock(return_value=True)) as complete,
        ):
            result = await front_webhook_module.process_inbox_event(claim.event_id)

        assert result == {"status": "ok"}
        complete.assert_awaited_once_with(claim.event_id, claim.lease_token)

    asyncio.run(case())


def test_claimed_ignored_event_is_terminal():
    async def case():
        claim = _claim_snapshot(event_id="evt_ignored")
        ignored = {"status": "ignored", "reason": "not inbound user message"}
        with (
            patch.object(front_webhook_module, "claim_webhook", AsyncMock(return_value=claim)),
            patch.object(
                front_webhook_module,
                "_process_front_webhook_event",
                AsyncMock(return_value=ignored),
            ),
            patch.object(front_webhook_module, "complete_webhook", AsyncMock(return_value=True)) as complete,
        ):
            result = await front_webhook_module.process_inbox_event(claim.event_id)

        assert result == ignored
        complete.assert_awaited_once_with(claim.event_id, claim.lease_token)

    asyncio.run(case())


def test_claimed_failure_is_scheduled_before_503_returns():
    async def case():
        claim = _claim_snapshot()
        retry = SimpleNamespace(status="retry", attempts=1)
        failure = HTTPException(status_code=503, detail="temporary")
        fail = AsyncMock(return_value=retry)
        with (
            patch.object(front_webhook_module, "claim_webhook", AsyncMock(return_value=claim)),
            patch.object(
                front_webhook_module,
                "_process_front_webhook_event",
                AsyncMock(side_effect=failure),
            ),
            patch.object(front_webhook_module, "fail_webhook", fail),
        ):
            try:
                await front_webhook_module.process_inbox_event(claim.event_id)
            except HTTPException as exc:
                assert exc.status_code == 503
            else:
                raise AssertionError("retryable processing failure must return 503")

        fail.assert_awaited_once_with(claim.event_id, claim.lease_token, failure)

    asyncio.run(case())
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Expected: FAIL because the route does not call the inbox service and `process_inbox_event` is missing.

- [ ] **Step 3: Wire durable enqueue and shared processing into the route**

Add service imports in `webhooks/front_webhook.py`:

```python
from services.webhook_inbox import (
    claim_webhook,
    complete_webhook,
    derive_event_id,
    enqueue_webhook,
    fail_webhook,
    get_webhook,
    list_due_event_ids,
)
```

Replace the final event-ID and processing portion of `front_webhook` with:

```python
    event_id = derive_event_id(payload, body)
    conversation = payload.get("conversation") or {}
    conversation_id = conversation.get("id") or payload.get("conversation_id")

    if not conversation_id:
        return {"status": "ignored", "reason": "no conversation_id"}

    try:
        await enqueue_webhook(event_id, conversation_id, payload)
    except Exception as exc:
        logger.exception("Could not persist Front webhook %s", event_id)
        raise HTTPException(status_code=503, detail="Webhook persistence failed") from exc

    return await process_inbox_event(event_id)
```

Move semaphore and conversation-lock ownership out of the route and add:

```python
async def _save_processing_failure(claim, error: Exception):
    try:
        outcome = await fail_webhook(claim.event_id, claim.lease_token, error)
    except Exception:
        logger.exception("Could not persist retry state for Front webhook %s", claim.event_id)
        return None
    if outcome is not None and outcome.status == "dead_letter":
        logger.error(
            "Front webhook moved to dead_letter event_id=%s conversation_id=%s attempts=%s",
            claim.event_id,
            claim.conversation_id,
            outcome.attempts,
        )
    return outcome


async def process_inbox_event(event_id: str):
    claim = await claim_webhook(event_id)
    if claim is None:
        current = await get_webhook(event_id)
        if current is not None and current.status == "processed":
            return {"status": "already_processed"}
        return {
            "status": "queued",
            "queue_status": current.status if current is not None else "missing",
        }

    try:
        async with _webhook_semaphore:
            lock = _get_conversation_lock(claim.conversation_id)
            async with lock:
                result = await _process_front_webhook_event(
                    claim.payload,
                    claim.event_id,
                    claim.conversation_id,
                )
    except HTTPException as exc:
        await _save_processing_failure(claim, exc)
        raise
    except Exception as exc:
        logger.exception("Unexpected queued webhook failure for %s", claim.event_id)
        await _save_processing_failure(claim, exc)
        raise HTTPException(status_code=503, detail="handler_error") from exc

    try:
        completed = await complete_webhook(claim.event_id, claim.lease_token)
    except Exception as exc:
        logger.exception("Could not complete Front webhook inbox row %s", claim.event_id)
        raise HTTPException(status_code=503, detail="Webhook completion failed") from exc
    if not completed:
        raise HTTPException(status_code=503, detail="Webhook processing lease lost")
    return result


async def retry_due_front_webhooks() -> dict[str, int]:
    event_ids = await list_due_event_ids(limit=20)
    result = {"due": len(event_ids), "processed": 0, "failed": 0}
    for event_id in event_ids:
        try:
            await process_inbox_event(event_id)
            result["processed"] += 1
        except HTTPException:
            result["failed"] += 1
        except Exception:
            result["failed"] += 1
            logger.exception("Retry loop failed for Front webhook %s", event_id)
    return result
```

Leave `_process_front_webhook_event` behavior unchanged so existing runtime-boundary tests continue to verify handler cleanup and truthful HTTP 503 semantics.

- [ ] **Step 4: Run focused and boundary tests**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_runtime_boundaries.py
```

Expected: both print their success messages.

- [ ] **Step 5: Commit the HTTP integration**

```bash
git add webhooks/front_webhook.py tests/test_webhook_recovery.py
git commit -m "feat: recover failed front webhook processing"
```

### Task 4: One-Minute Scheduler Recovery Job

**Files:**
- Modify: `tasks/scheduler.py`
- Modify: `tests/test_webhook_recovery.py`
- Do not stage: existing draft-adoption hunks in `tasks/scheduler.py`

- [ ] **Step 1: Add a failing scheduler registration test**

Add this source-level regression to `tests/test_webhook_recovery.py`:

```python
def test_scheduler_registers_bounded_webhook_retry_job():
    source = Path("tasks/scheduler.py").read_text()
    assert "retry_due_front_webhooks" in source
    assert 'id="retry_pending_front_webhooks_every_minute"' in source
    assert "minutes=1" in source
    assert "coalesce=True" in source
    assert "max_instances=1" in source
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Expected: FAIL on the missing scheduler job ID.

- [ ] **Step 3: Add the isolated scheduler wrapper and registration**

In `tasks/scheduler.py`, add this function without changing
`refresh_draft_adoption_metrics`:

```python
async def retry_pending_front_webhooks():
    try:
        from webhooks.front_webhook import retry_due_front_webhooks

        result = await retry_due_front_webhooks()
        if result["due"]:
            logger.info("Retried pending Front webhooks: %s", result)
    except Exception:
        logger.exception("retry_pending_front_webhooks failed")
```

Register it in `start_scheduler()`:

```python
    scheduler.add_job(
        retry_pending_front_webhooks,
        "interval",
        minutes=1,
        id="retry_pending_front_webhooks_every_minute",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
```

- [ ] **Step 4: Run scheduler, routing, and recovery tests**

Run:

```bash
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_routing.py
```

Expected: both pass, including the existing draft-adoption scheduler assertion.

- [ ] **Step 5: Stage only the retry-related scheduler hunks and commit**

First inspect the mixed file:

```bash
git diff -- tasks/scheduler.py
```

Stage `tests/test_webhook_recovery.py` normally. Apply this exact patch to the
index so the pre-existing draft-adoption working-tree hunks remain unstaged:

```bash
git add tests/test_webhook_recovery.py
git apply --cached --unidiff-zero <<'PATCH'
diff --git a/tasks/scheduler.py b/tasks/scheduler.py
--- a/tasks/scheduler.py
+++ b/tasks/scheduler.py
@@ -143,0 +144,11 @@
+async def retry_pending_front_webhooks():
+    try:
+        from webhooks.front_webhook import retry_due_front_webhooks
+
+        result = await retry_due_front_webhooks()
+        if result["due"]:
+            logger.info("Retried pending Front webhooks: %s", result)
+    except Exception:
+        logger.exception("retry_pending_front_webhooks failed")
+
+
@@ -169,0 +181,9 @@
+    scheduler.add_job(
+        retry_pending_front_webhooks,
+        "interval",
+        minutes=1,
+        id="retry_pending_front_webhooks_every_minute",
+        replace_existing=True,
+        coalesce=True,
+        max_instances=1,
+    )
PATCH
```

Verify before committing:

```bash
git diff --cached -- tasks/scheduler.py tests/test_webhook_recovery.py
git diff -- tasks/scheduler.py
```

Expected: cached scheduler diff contains only `retry_pending_front_webhooks`
and its `add_job`; the unstaged diff still contains
`refresh_draft_adoption_metrics`.

Commit:

```bash
git commit -m "feat: schedule front webhook recovery"
```

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/runtime-boundaries.md`
- Modify: `CLAUDE.md`
- Modify: `record.md`

- [ ] **Step 1: Update operator and repository documentation**

Document these exact facts in all relevant existing sections:

```text
- Valid conversation webhooks are committed to webhook_inbox before processing.
- Normal processing is still immediate in the request path.
- Internal APScheduler retry runs every minute; Front Rule Webhooks themselves do not retry.
- Retry delays are 1, 5, 15, 60, and 180 minutes after the immediate attempt.
- Attempt 6 failure becomes dead_letter and is logged for manual review.
- A 15-minute lease recovers processing rows abandoned by a process crash.
- Processed inbox payloads are cleared; dead-letter payloads remain recoverable.
- webhook_events continues to count only successful or deterministically ignored events.
```

Add `webhook_inbox` to the README data model and add this verification command
before the existing runtime-boundary test:

```bash
.venv/bin/python tests/test_webhook_recovery.py
```

Update `CLAUDE.md` idempotency and failure semantics so future work does not
reintroduce the incorrect assumption that Front performs retries.

- [ ] **Step 2: Append the required record entry**

Append under the existing `## 2026-07-14` heading in `record.md`:

```markdown
- [feat] persist authenticated Front webhooks before processing and retry temporary failures with leased SQLite inbox records and APScheduler (models.py, services/webhook_inbox.py, webhooks/front_webhook.py, tasks/scheduler.py, tests/test_webhook_recovery.py)
- [docs] document durable webhook recovery, retry timing, dead letters, and verification (README.md, CLAUDE.md, docs/runtime-boundaries.md)
```

- [ ] **Step 3: Run the complete offline regression suite**

Run each command independently:

```bash
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent services tasks tools webhooks tests config.py main.py models.py
.venv/bin/python -m pip check
git diff --check
```

Expected: all test scripts print success, compileall and `pip check` produce no
errors, and `git diff --check` produces no output.

- [ ] **Step 4: Verify schema creation without touching production data**

Run an isolated temporary-database smoke test:

```bash
DATABASE_URL=sqlite+aiosqlite:////tmp/front-agent-webhook-recovery-smoke.db \
FRONT_API_TOKEN=test OPENAI_API_KEY=test LINEAR_API_KEY=test LINEAR_TEAM_ID=test \
.venv/bin/python -c 'import asyncio, models; from database import init_db; asyncio.run(init_db())'
sqlite3 /tmp/front-agent-webhook-recovery-smoke.db '.schema webhook_inbox'
```

Expected: the schema includes the event primary key, payload, status, attempts,
availability, lease, error, and timestamp columns.

- [ ] **Step 5: Review repository boundaries and commit documentation**

Verify only intended implementation files are staged and the user's unrelated
changes remain unstaged:

```bash
git status --short
git diff --cached --check
git diff --check
```

Then commit documentation and the required record entry:

```bash
git add README.md CLAUDE.md docs/runtime-boundaries.md record.md
git commit -m "docs: explain durable webhook recovery"
```

- [ ] **Step 6: Final commit and runtime audit**

Run:

```bash
git log -6 --oneline
git status --short
git diff -- routes/ops.py tasks/scheduler.py tests/test_routing.py
```

Expected: implementation commits are present; `routes/ops.py`, the original
draft-adoption scheduler/test work, and any other pre-existing user changes are
still intact. No production restart or live webhook is performed at this stage.
