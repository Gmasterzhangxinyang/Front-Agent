import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import ConversationAction, SybilNotification
import routes.ops as ops_module
import tools.sybil_digest as sybil_digest_module


async def _with_database(case):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        with (
            patch.object(ops_module, "AsyncSessionLocal", sessions),
            patch.object(sybil_digest_module, "AsyncSessionLocal", sessions),
        ):
            await case(sessions)
    finally:
        await engine.dispose()


async def _insert_notification(sessions, *, status="pending", error=""):
    async with sessions() as db:
        item = SybilNotification(
            conversation_id="cnv_sybil",
            message="education review",
            handoff_type="education_review",
            linear_url="https://linear.example/CUS-1",
            status=status,
            error=error,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item.id



def test_pending_row_is_retained_as_dismissed_with_one_audit_action():
    async def case(sessions):
        item_id = await _insert_notification(sessions)
        response = await ops_module.dismiss_sybil_notification(item_id)
        repeated = await ops_module.dismiss_sybil_notification(item_id)

        assert response["item"]["status"] == "dismissed"
        assert repeated["item"]["status"] == "dismissed"
        async with sessions() as db:
            item = await db.get(SybilNotification, item_id)
            assert item is not None
            assert item.status == "dismissed"
            assert item.message == "education review"
            assert item.linear_url == "https://linear.example/CUS-1"
            actions = await db.execute(
                select(ConversationAction).where(
                    ConversationAction.conversation_id == "cnv_sybil",
                    ConversationAction.action_type == "sybil_dismiss",
                    ConversationAction.action_key == f"notification:{item_id}",
                )
            )
            rows = actions.scalars().all()
            assert len(rows) == 1
            assert rows[0].result == "dismissed"

    asyncio.run(_with_database(case))


def test_sent_row_cannot_be_dismissed():
    async def case(sessions):
        item_id = await _insert_notification(sessions, status="sent")
        try:
            await ops_module.dismiss_sybil_notification(item_id)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("sent notification must be immutable")
        async with sessions() as db:
            assert (await db.get(SybilNotification, item_id)).status == "sent"

    asyncio.run(_with_database(case))


def test_unknown_notification_returns_404():
    async def case(_sessions):
        try:
            await ops_module.dismiss_sybil_notification(999)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("unknown notification must return 404")

    asyncio.run(_with_database(case))


def test_digest_claim_prevents_successful_dismiss_during_send():
    async def case(sessions):
        item_id = await _insert_notification(sessions)
        send_started = asyncio.Event()
        release_send = asyncio.Event()

        async def paused_send(_text):
            send_started.set()
            await release_send.wait()
            return True

        with patch.object(
            sybil_digest_module.feishu,
            "send_sybil_group_text",
            paused_send,
        ):
            digest_task = asyncio.create_task(
                sybil_digest_module.send_pending_sybil_digest()
            )
            await asyncio.wait_for(send_started.wait(), timeout=1)

            listing = await ops_module.list_sybil(limit=100)
            sending_item = next(item for item in listing["items"] if item["id"] == item_id)
            assert sending_item["status"] == "sending"
            assert sending_item["error"] == ""

            try:
                await ops_module.dismiss_sybil_notification(item_id)
            except HTTPException as exc:
                assert exc.status_code == 409
                dismissed_during_send = False
            else:
                dismissed_during_send = True

            release_send.set()
            result = await asyncio.wait_for(digest_task, timeout=1)

        assert not dismissed_during_send, "an in-flight digest must not report dismissal"
        assert result["sent_count"] == 1
        async with sessions() as db:
            item = await db.get(SybilNotification, item_id)
            assert item.status == "sent"

    asyncio.run(_with_database(case))


def test_digest_send_exception_restores_claim_to_pending():
    async def case(sessions):
        item_id = await _insert_notification(sessions)

        async def failing_send(_text):
            raise RuntimeError("temporary Feishu failure")

        with (
            patch.object(
                sybil_digest_module.feishu,
                "send_sybil_group_text",
                failing_send,
            ),
            patch.object(sybil_digest_module.logger, "exception") as logged,
        ):
            result = await sybil_digest_module.send_pending_sybil_digest()

        logged.assert_called_once()
        assert result == {"ok": False, "sent_count": 0, "pending_count": 1}
        async with sessions() as db:
            item = await db.get(SybilNotification, item_id)
            assert item.status == "pending"
            assert item.error == "Feishu digest send failed"

    asyncio.run(_with_database(case))


def test_expired_digest_claim_is_recovered_and_sent():
    async def case(sessions):
        item_id = await _insert_notification(
            sessions,
            status="sending",
            error="digest-lease:0:abandoned",
        )

        async def successful_send(_text):
            return True

        with patch.object(
            sybil_digest_module.feishu,
            "send_sybil_group_text",
            successful_send,
        ):
            result = await sybil_digest_module.send_pending_sybil_digest()

        assert result == {"ok": True, "sent_count": 1}
        async with sessions() as db:
            item = await db.get(SybilNotification, item_id)
            assert item.status == "sent"
            assert item.error == ""

    asyncio.run(_with_database(case))


def test_invalid_future_digest_lease_is_treated_as_expired():
    assert sybil_digest_module._sending_lease_expired(
        "digest-lease:9999999999:"
    )
    assert sybil_digest_module._sending_lease_expired(
        "digest-lease:9999999999:+0000000000000000000000000000000"
    )


def test_digest_still_selects_pending_notifications_only():
    source = Path("tools/sybil_digest.py").read_text()
    assert "SybilNotification.status == PENDING" in source
    assert 'PENDING = "pending"' in source




def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("ops sybil dismissal tests passed")
