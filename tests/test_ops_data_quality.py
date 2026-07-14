import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import ConversationState, SybilNotification, WebhookInbox
import routes.ops as ops_routes
import services.ops_metadata as ops_metadata


@asynccontextmanager
async def _isolated_sessions():
    with TemporaryDirectory() as tmp:
        database_path = Path(tmp) / "ops-metadata.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{database_path}",
            echo=False,
        )
        session_factory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            yield session_factory
        finally:
            await engine.dispose()


def test_extract_front_metadata_uses_recipient_and_subject():
    sender, summary = ops_metadata.extract_front_metadata(
        {
            "recipient": {"handle": "customer@example.com"},
            "subject": "  Cannot access my workspace  ",
        }
    )

    assert sender == "customer@example.com"
    assert summary == "Cannot access my workspace"


def test_enrichment_prioritizes_actionable_missing_rows():
    async def run_case():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        attention_updated_at = now - timedelta(days=2)
        async with _isolated_sessions() as session_factory:
            async with session_factory() as db:
                db.add_all(
                    [
                        ConversationState(
                            conversation_id="cnv_done",
                            category="technical",
                            step="done",
                            payload={},
                            updated_at=now,
                        ),
                        ConversationState(
                            conversation_id="cnv_attention",
                            category="account",
                            step="failed_needs_review",
                            payload={},
                            updated_at=attention_updated_at,
                        ),
                        ConversationState(
                            conversation_id="cnv_complete",
                            sender_email="known@example.com",
                            category="billing",
                            step="manual_review",
                            payload={"summary": "Already complete"},
                            updated_at=now,
                        ),
                    ]
                )
                await db.commit()

                fetch = AsyncMock(
                    return_value={
                        "recipient": {"handle": "priority@example.com"},
                        "subject": "Priority account failure",
                    }
                )
                with patch.object(ops_metadata, "get_conversation", fetch):
                    result = await ops_metadata.enrich_missing_conversation_metadata(
                        db,
                        limit=1,
                    )

                priority = await db.get(ConversationState, "cnv_attention")
                done = await db.get(ConversationState, "cnv_done")

        assert result == {
            "selected": 1,
            "updated": 1,
            "unchanged": 0,
            "failed": 0,
        }
        fetch.assert_awaited_once_with("cnv_attention")
        assert priority.sender_email == "priority@example.com"
        assert priority.payload["summary"] == "Priority account failure"
        assert priority.updated_at == attention_updated_at
        assert ops_metadata.METADATA_CHECKED_AT_KEY in priority.payload
        assert not done.sender_email
        assert not done.payload.get("summary")

    asyncio.run(run_case())


def test_enrichment_preserves_existing_values():
    async def run_case():
        async with _isolated_sessions() as session_factory:
            async with session_factory() as db:
                db.add(
                    ConversationState(
                        conversation_id="cnv_partial",
                        sender_email="original@example.com",
                        category="technical",
                        step="manual_review",
                        payload={},
                    )
                )
                await db.commit()

                with patch.object(
                    ops_metadata,
                    "get_conversation",
                    AsyncMock(
                        return_value={
                            "recipient": {"handle": "replacement@example.com"},
                            "subject": "Recovered subject",
                        }
                    ),
                ):
                    await ops_metadata.enrich_missing_conversation_metadata(
                        db,
                        limit=5,
                    )

                stored = await db.get(ConversationState, "cnv_partial")

        assert stored.sender_email == "original@example.com"
        assert stored.payload["summary"] == "Recovered subject"

    asyncio.run(run_case())


def test_ops_summary_exposes_actionable_health_and_coverage():
    async def run_case():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with _isolated_sessions() as session_factory:
            async with session_factory() as db:
                db.add_all(
                    [
                        ConversationState(
                            conversation_id="cnv_failed",
                            category="account",
                            step="failed_needs_review",
                            payload={},
                            updated_at=now,
                        ),
                        ConversationState(
                            conversation_id="cnv_complete",
                            sender_email="known@example.com",
                            category="technical",
                            sub_type="how_to",
                            step="draft_created",
                            payload={"summary": "Known issue"},
                            updated_at=now,
                        ),
                        ConversationState(
                            conversation_id="cnv_reason",
                            sender_email="reason@example.com",
                            category="technical",
                            sub_type="how_to",
                            step="done",
                            payload={"reason": "Existing routing reason"},
                            updated_at=now,
                        ),
                        WebhookInbox(
                            event_id="evt_retry",
                            conversation_id="cnv_failed",
                            payload={"id": "evt_retry"},
                            status="retry",
                            attempts=2,
                            available_at=now - timedelta(minutes=1),
                            last_error="provider timeout",
                            created_at=now - timedelta(minutes=5),
                            updated_at=now,
                        ),
                        WebhookInbox(
                            event_id="evt_processed",
                            conversation_id="cnv_complete",
                            payload={},
                            status="processed",
                            attempts=1,
                            available_at=now,
                            last_error="",
                            created_at=now,
                            updated_at=now,
                            processed_at=now,
                        ),
                        SybilNotification(
                            conversation_id="cnv_failed",
                            message="Needs review",
                            status="pending",
                        ),
                    ]
                )
                await db.commit()

            with patch.object(
                ops_routes,
                "AsyncSessionLocal",
                session_factory,
            ):
                summary = await ops_routes.ops_summary()

        assert summary["service"]["status"] == "degraded"
        assert summary["metrics"]["attention_count"] == 1
        assert summary["metrics"]["pending_sybil_count"] == 1
        assert summary["metrics"]["webhook_queue_count"] == 1
        assert summary["automation_health"]["webhook_due_count"] == 1
        assert summary["automation_health"]["webhook_inbox_by_status"] == {
            "processed": 1,
            "retry": 1,
        }
        assert (
            summary["automation_health"]["webhook_problem_items"][0]["event_id"]
            == "evt_retry"
        )
        assert summary["data_health"]["recent_30d_rows"] == 3
        assert summary["data_health"]["recent_30d_complete"] == 2
        assert summary["data_health"]["recent_30d_coverage_rate"] == 66.7
        assert summary["data_health"]["attention_missing_count"] == 1
        assert summary["priority_items"][0]["conversation_id"] == "cnv_failed"

    asyncio.run(run_case())


def test_ops_page_marks_historical_gaps_and_exposes_health_panels():
    source = Path("routes/static/ops.html").read_text()

    for required_id in (
        "priority-table",
        "automation-health",
        "webhook-problems",
        "data-health",
        "service-dot",
    ):
        assert f'id="{required_id}"' in source
    assert "missingValue()" in source
    assert 'class="kpi-strip"' in source
    assert 'class="priority-table"' in source
    assert "item.sender_email||'-'" not in source
    assert "renderAttention" not in source
    for removed_id in (
        "opportunity-list",
        "friction-bars",
        "recent-actions-table",
        "category-bars",
        "step-bars",
        "sybil-summary",
        "opportunity-insights",
        "experience-insights",
        "risk-insights",
    ):
        assert f'id="{removed_id}"' not in source


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("ops data quality tests passed")
