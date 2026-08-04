import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import ConversationAction, ConversationState, DraftAdoption
import services.draft_adoption as draft_adoption_module
from services.draft_adoption import (
    STATUS_EXACT_ADOPTED,
    STATUS_HANDLED_WITHOUT_SEND,
    STATUS_NO_FOLLOWUP,
    STATUS_MODIFIED_OR_MANUAL,
    STATUS_NOT_SENT,
    STATUS_PENDING_REVIEW,
    STATUS_WAITING,
    TRACKING_START_AT,
    classify_draft_adoption,
    draft_adoption_metrics,
    effective_since,
    text_hash,
)


def test_exact_draft_adoption_matches_body_hash():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    body = "Thanks for reaching out. Please try the documented workflow setting."
    result = classify_draft_adoption(
        text_hash(body),
        created_at,
        [
            {
                "type": "email",
                "is_inbound": False,
                "is_draft": False,
                "created_at": "2026-07-01T10:05:00",
                "text": body,
            }
        ],
        now=created_at + timedelta(hours=2),
    )
    assert result.status == STATUS_EXACT_ADOPTED
    assert result.sent_at == datetime(2026, 7, 1, 10, 5, 0)


def test_modified_or_manual_when_outbound_differs():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("original draft"),
        created_at,
        [
            {
                "type": "email",
                "is_inbound": False,
                "is_draft": False,
                "created_at": "2026-07-01T10:30:00",
                "text": "human edited reply",
            }
        ],
        now=created_at + timedelta(hours=2),
    )
    assert result.status == STATUS_MODIFIED_OR_MANUAL


def test_pending_then_no_followup_without_outbound():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    draft_hash = text_hash("draft")
    pending = classify_draft_adoption(draft_hash, created_at, [], now=created_at + timedelta(hours=2))
    stale = classify_draft_adoption(draft_hash, created_at, [], now=created_at + timedelta(hours=25))
    assert pending.status == STATUS_PENDING_REVIEW
    assert stale.status == STATUS_NO_FOLLOWUP


def test_internal_teammate_reply_is_detected_even_when_front_marks_it_inbound():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [
            {
                "type": "email",
                "is_inbound": True,
                "is_draft": False,
                "author": {"email": "teammate@dify.ai"},
                "created_at": "2026-07-01T10:30:00",
                "text": "edited teammate reply",
            }
        ],
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_MODIFIED_OR_MANUAL


def test_internal_forward_envelope_without_author_is_not_a_customer_reply():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [
            {
                "type": "email",
                "is_inbound": True,
                "is_draft": False,
                "created_at": "2026-07-01T10:30:00",
                "text": "forwarded envelope",
            }
        ],
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_NO_FOLLOWUP


def test_comment_after_draft_is_handled_without_send():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [],
        comments=[
            {"posted_at": "2026-07-01T10:01:00", "body": "[AI草稿] 自动记录"},
            {"posted_at": "2026-07-01T10:05:00", "body": "进入工单"},
        ],
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_HANDLED_WITHOUT_SEND

def test_latest_waiting_comment_keeps_case_out_of_handled_count():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [],
        comments=[
            {"posted_at": "2026-07-01T10:05:00", "body": "已转交法务团队"},
            {"posted_at": "2026-07-01T10:10:00", "body": "asking 汤圆"},
        ],
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_WAITING


def test_internal_team_transfer_comment_is_still_waiting():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [],
        comments=[
            {"posted_at": "2026-07-01T10:10:00", "body": "已转交法务团队"},
        ],
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_WAITING


def test_workflow_action_after_draft_is_handled_without_send():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [],
        workflow_actions={"linear_create_ticket"},
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_HANDLED_WITHOUT_SEND


def test_waiting_state_is_not_reported_as_no_followup():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [],
        state_step="awaiting_customer",
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_WAITING


def test_auto_draft_comment_alone_is_not_handling_evidence():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("draft"),
        created_at,
        [],
        comments=[
            {"posted_at": "2026-07-01T10:01:00", "body": "[AI草稿] 自动记录"}
        ],
        conversation_status="archived",
        now=created_at + timedelta(hours=25),
    )
    assert result.status == STATUS_NO_FOLLOWUP


def test_effective_since_does_not_scan_before_rollout():
    assert effective_since(datetime(2026, 1, 1, 0, 0, 0)) == TRACKING_START_AT
    later = TRACKING_START_AT + timedelta(minutes=1)
    assert effective_since(later) == later


def test_refresh_releases_sqlite_before_front_network_call():
    async def run_case():
        with TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "draft-adoption.db"
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{database_path}",
                connect_args={"timeout": 0.1},
            )
            sessions = sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            try:
                async with sessions() as db:
                    action = ConversationAction(
                        conversation_id="cnv_draft",
                        action_type="front_create_draft",
                        action_key=f"body:{text_hash('draft body')}",
                        result="draft_created",
                        created_at=(
                            datetime.now(timezone.utc).replace(tzinfo=None)
                            - timedelta(hours=1)
                        ),
                    )
                    db.add(action)
                    await db.commit()
                    action_id = action.id

                    async def fetch_messages(_conversation_id):
                        async with sessions() as writer:
                            writer.add(
                                ConversationState(
                                    conversation_id="cnv_parallel_write",
                                    category="technical",
                                    step="done",
                                    payload={},
                                )
                            )
                            await asyncio.wait_for(writer.commit(), timeout=2)
                        return []

                    with (
                        patch.object(
                            draft_adoption_module,
                            "get_conversation_messages",
                            fetch_messages,
                        ),
                        patch.object(
                            draft_adoption_module,
                            "get_conversation_comments",
                            AsyncMock(return_value=[]),
                        ),
                        patch.object(
                            draft_adoption_module,
                            "get_conversation",
                            AsyncMock(return_value={"status": "archived"}),
                        ),
                    ):
                        result = await draft_adoption_module.refresh_draft_adoptions(
                            db,
                            since=TRACKING_START_AT,
                            limit=5,
                        )

                    adoption = await db.get(DraftAdoption, action_id)
                    parallel = await db.get(
                        ConversationState,
                        "cnv_parallel_write",
                    )

                assert result == {
                    "checked": 1,
                    "refreshed": 1,
                    "skipped": 0,
                    "failed": 0,
                }
                assert adoption is not None
                assert parallel is not None
            finally:
                await engine.dispose()

    asyncio.run(run_case())


def test_legacy_not_sent_rows_are_refreshed_when_a_reply_appears():
    async def run_case():
        with TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "legacy-not-sent.db"
            engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
            sessions = sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            try:
                async with sessions() as db:
                    created_at = (
                        datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(hours=48)
                    )
                    body = "draft body"
                    action = ConversationAction(
                        conversation_id="cnv_legacy",
                        action_type="front_create_draft",
                        action_key=f"body:{text_hash(body)}",
                        result="draft_created",
                        created_at=created_at,
                    )
                    db.add(action)
                    await db.flush()
                    db.add(
                        DraftAdoption(
                            action_id=action.id,
                            conversation_id=action.conversation_id,
                            action_key=action.action_key,
                            draft_hash=text_hash(body),
                            status=STATUS_NOT_SENT,
                            checked_at=created_at + timedelta(hours=25),
                            draft_created_at=created_at,
                        )
                    )
                    await db.commit()

                    messages = [
                        {
                            "type": "email",
                            "is_inbound": False,
                            "is_draft": False,
                            "created_at": created_at + timedelta(hours=26),
                            "text": body,
                        }
                    ]
                    with patch.object(
                        draft_adoption_module,
                        "get_conversation_messages",
                        AsyncMock(return_value=messages),
                    ):
                        result = await draft_adoption_module.refresh_draft_adoptions(
                            db,
                            since=TRACKING_START_AT,
                            limit=5,
                        )

                    adoption = await db.get(DraftAdoption, action.id)
                    assert result["refreshed"] == 1
                    assert result["skipped"] == 0
                    assert adoption.status == STATUS_EXACT_ADOPTED
            finally:
                await engine.dispose()

    asyncio.run(run_case())


def test_metrics_separate_reply_quality_from_workflow_outcomes():
    async def run_case():
        with TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "draft-metrics.db"
            engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
            sessions = sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            created_at = TRACKING_START_AT + timedelta(days=1)
            cases = [
                ("cnv_exact", "customer1@example.com", STATUS_EXACT_ADOPTED),
                ("cnv_modified", "customer2@example.com", STATUS_MODIFIED_OR_MANUAL),
                ("cnv_ticket", "customer3@example.com", STATUS_HANDLED_WITHOUT_SEND),
                ("cnv_waiting", "customer4@example.com", STATUS_WAITING),
                ("cnv_no_followup", "customer5@example.com", STATUS_NO_FOLLOWUP),
                (
                    "cnv_forwarded_customer",
                    "staff@dify.ai",
                    STATUS_MODIFIED_OR_MANUAL,
                ),
                ("cnv_1j36t6hn", "staff@dify.ai", STATUS_EXACT_ADOPTED),
                ("cnv_test_case", "customer6@example.com", STATUS_EXACT_ADOPTED),
            ]

            try:
                async with sessions() as db:
                    for conversation_id, sender_email, status in cases:
                        db.add(
                            ConversationState(
                                conversation_id=conversation_id,
                                sender_email=sender_email,
                                category="technical",
                                step="done",
                                payload={},
                            )
                        )
                        action = ConversationAction(
                            conversation_id=conversation_id,
                            action_type="front_create_draft",
                            action_key=f"body:{text_hash(conversation_id)}",
                            result="draft_created",
                            created_at=created_at,
                        )
                        db.add(action)
                        await db.flush()
                        db.add(
                            DraftAdoption(
                                action_id=action.id,
                                conversation_id=conversation_id,
                                action_key=action.action_key,
                                draft_hash=text_hash(conversation_id),
                                status=status,
                                checked_at=created_at,
                                draft_created_at=created_at,
                            )
                        )
                    await db.commit()
                    metrics = await draft_adoption_metrics(
                        db,
                        since=TRACKING_START_AT,
                    )

                assert metrics["draft_actions"] == 6
                assert metrics["tracked_drafts"] == 6
                assert metrics["responded_drafts"] == 3
                assert metrics["handled_without_send"] == 1
                assert metrics["waiting"] == 1
                assert metrics["no_followup_detected"] == 1
                assert metrics["direct_adoption_rate"] == 33.3
                assert metrics["response_detected_rate"] == 50.0
                assert metrics["handled_rate"] == 66.7
            finally:
                await engine.dispose()

    asyncio.run(run_case())


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("draft adoption tests passed")
