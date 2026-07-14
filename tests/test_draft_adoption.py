import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import ConversationAction, ConversationState, DraftAdoption
import services.draft_adoption as draft_adoption_module
from services.draft_adoption import (
    STATUS_EXACT_ADOPTED,
    STATUS_MODIFIED_OR_MANUAL,
    STATUS_NOT_SENT,
    STATUS_PENDING_REVIEW,
    TRACKING_START_AT,
    classify_draft_adoption,
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


def test_pending_then_not_sent_without_outbound():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    draft_hash = text_hash("draft")
    pending = classify_draft_adoption(draft_hash, created_at, [], now=created_at + timedelta(hours=2))
    stale = classify_draft_adoption(draft_hash, created_at, [], now=created_at + timedelta(hours=25))
    assert pending.status == STATUS_PENDING_REVIEW
    assert stale.status == STATUS_NOT_SENT


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

                    with patch.object(
                        draft_adoption_module,
                        "get_conversation_messages",
                        fetch_messages,
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


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("draft adoption tests passed")
