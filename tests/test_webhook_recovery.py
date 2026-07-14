import asyncio
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import WebhookInbox
import services.webhook_inbox as webhook_inbox
from services.webhook_inbox import derive_event_id


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


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("webhook recovery tests passed")
