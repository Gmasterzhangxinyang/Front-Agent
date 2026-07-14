import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent.tool_registry as tool_registry
from agent.tool_registry import (
    ToolExecutionContext,
    execute_tool_call,
    prepare_llm_tool_call,
)
from database import Base
from models import ConversationAction


@asynccontextmanager
async def _isolated_sessions():
    with TemporaryDirectory() as tmp:
        database_path = Path(tmp) / "linear-dedupe.db"
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


def _ticket_args(
    conversation_id: str,
    *,
    sender_email: str = "person@example.com",
    original_message: str = "The same error happens every time.",
    title: str = "Generated title",
) -> dict:
    return {
        "conversation_id": conversation_id,
        "title": title,
        "body": f"Generated body for {conversation_id}",
        "sender_email": sender_email,
        "original_message": original_message,
    }


def test_linear_context_overrides_model_dedupe_inputs():
    prepared = prepare_llm_tool_call(
        "linear_create_ticket",
        {
            "conversation_id": "cnv_attacker",
            "title": "Issue",
            "body": "Details",
            "sender_email": "attacker@example.com",
            "original_message": "different content",
        },
        ToolExecutionContext(
            conversation_id="cnv_trusted",
            sender_email="person@example.com",
            original_message="trusted original email",
        ),
    )

    assert prepared["conversation_id"] == "cnv_trusted"
    assert prepared["sender_email"] == "person@example.com"
    assert prepared["original_message"] == "trusted original email"


def test_linear_identity_matches_same_sender_and_original_message():
    first = tool_registry._action_identity(
        "linear_create_ticket",
        _ticket_args("cnv_first", title="First generated title"),
    )
    second = tool_registry._action_identity(
        "linear_create_ticket",
        _ticket_args(
            "cnv_second",
            sender_email=" PERSON@EXAMPLE.COM ",
            title="Second generated title",
        ),
    )
    other_sender = tool_registry._action_identity(
        "linear_create_ticket",
        _ticket_args("cnv_third", sender_email="other@example.com"),
    )
    other_message = tool_registry._action_identity(
        "linear_create_ticket",
        _ticket_args("cnv_fourth", original_message="A different error."),
    )

    assert first is not None and second is not None
    assert first[2] == second[2]
    assert first[2] != other_sender[2]
    assert first[2] != other_message[2]


def test_simultaneous_duplicate_emails_create_one_linear_ticket():
    async def run_case():
        async with _isolated_sessions() as session_factory:
            release = asyncio.Event()
            create_calls = 0

            async def create_ticket(_title, _body):
                nonlocal create_calls
                create_calls += 1
                await release.wait()
                return "https://linear.app/acme/issue/CUS-42", "CUS-42"

            async with (
                session_factory() as first_db,
                session_factory() as second_db,
            ):
                with (
                    patch.object(
                        tool_registry.linear,
                        "create_ticket",
                        AsyncMock(side_effect=create_ticket),
                    ),
                    patch.object(
                        tool_registry,
                        "_safe_add_comment",
                        AsyncMock(return_value=True),
                    ),
                    patch.object(
                        tool_registry,
                        "_safe_reopen_conversation",
                        AsyncMock(return_value=True),
                    ),
                ):
                    first = asyncio.create_task(
                        execute_tool_call(
                            "linear_create_ticket",
                            _ticket_args("cnv_first", title="First title"),
                            first_db,
                        )
                    )
                    second = asyncio.create_task(
                        execute_tool_call(
                            "linear_create_ticket",
                            _ticket_args("cnv_second", title="Second title"),
                            second_db,
                        )
                    )
                    await asyncio.sleep(0.05)
                    calls_while_overlapping = create_calls
                    release.set()
                    results = await asyncio.gather(first, second)

            async with session_factory() as db:
                rows = (
                    await db.execute(
                        select(ConversationAction).where(
                            ConversationAction.action_type
                            == "linear_create_ticket"
                        )
                    )
                ).scalars().all()

        assert calls_while_overlapping == 1
        assert create_calls == 1
        assert len(rows) == 1
        assert json.loads(results[0])["identifier"] == "CUS-42"
        assert results[0] == results[1]

    asyncio.run(run_case())


def test_same_email_can_create_a_new_ticket_after_24_hours():
    async def run_case():
        args = _ticket_args("cnv_new")
        identity = tool_registry._action_identity(
            "linear_create_ticket",
            args,
        )
        assert identity is not None

        async with _isolated_sessions() as session_factory:
            async with session_factory() as db:
                db.add(
                    ConversationAction(
                        conversation_id="cnv_old",
                        action_type=identity[1],
                        action_key=identity[2],
                        result=json.dumps(
                            {
                                "status": "ticket_created",
                                "url": "https://linear.app/old",
                                "identifier": "CUS-OLD",
                            }
                        ),
                        created_at=(
                            datetime.now(timezone.utc).replace(tzinfo=None)
                            - timedelta(hours=25)
                        ),
                    )
                )
                await db.commit()

                with (
                    patch.object(
                        tool_registry.linear,
                        "create_ticket",
                        AsyncMock(
                            return_value=(
                                "https://linear.app/new",
                                "CUS-NEW",
                            )
                        ),
                    ) as create,
                    patch.object(
                        tool_registry,
                        "_safe_add_comment",
                        AsyncMock(return_value=True),
                    ),
                    patch.object(
                        tool_registry,
                        "_safe_reopen_conversation",
                        AsyncMock(return_value=True),
                    ),
                ):
                    result = await execute_tool_call(
                        "linear_create_ticket",
                        args,
                        db,
                    )

                create.assert_awaited_once()
                called_title, called_body = create.await_args.args
                assert called_title == args["title"]
                assert called_body.startswith(args["body"])
                assert json.loads(result)["identifier"] == "CUS-NEW"

    asyncio.run(run_case())


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("linear ticket deduplication tests passed")
