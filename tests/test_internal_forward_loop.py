import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent.orchestrator as orchestrator_module
import webhooks.front_webhook as front_webhook_module
from agent.message_identity import external_sender_email
from tools import state as state_tool


class _ScalarResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, statement):
        return _ScalarResult()

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def _observed_internal_forward_message(*, is_draft=False):
    """Shape observed on cnv_1j8hf2sb after Bobby replied in Front."""
    return {
        "id": "msg_internal_forward",
        "type": "email",
        "is_inbound": True,
        "is_draft": is_draft,
        "author": {"email": "bobby@dify.ai"},
        "recipients": [
            {"role": "from", "handle": "support@dify.ai"},
            {"role": "to", "handle": "bobby@dify.ai"},
        ],
        "text": "Manually edited internal reply",
    }


def _external_customer_message():
    return {
        "id": "msg_customer_reply",
        "type": "email",
        "is_inbound": True,
        "is_draft": False,
        "recipients": [
            {"role": "from", "handle": "student@example.edu"},
            {"role": "to", "handle": "support@dify.ai"},
        ],
        "text": "Customer reply",
    }


def test_internal_forward_reply_is_not_a_processable_customer_message():
    message = _observed_internal_forward_message()

    assert not front_webhook_module._is_processable_inbound_message(message)
    assert external_sender_email(message) == ""

    customer_message = _external_customer_message()
    assert front_webhook_module._is_processable_inbound_message(customer_message)
    assert external_sender_email(customer_message) == "student@example.edu"


def test_internal_forward_is_support_context_and_unsent_draft_is_excluded():
    conversation = orchestrator_module.build_conversation_text(
        [
            _external_customer_message(),
            _observed_internal_forward_message(),
            _observed_internal_forward_message(is_draft=True),
        ]
    )

    assert "[User]: Customer reply" in conversation
    assert "[Support]: Manually edited internal reply" in conversation
    assert conversation.count("Manually edited internal reply") == 1


def test_internal_forward_event_is_terminally_ignored_before_agent_handling():
    async def run_case():
        session = _FakeSession()
        handle_email = AsyncMock()
        payload = {"target": {"data": _observed_internal_forward_message()}}

        with (
            patch.object(
                front_webhook_module,
                "AsyncSessionLocal",
                lambda: session,
            ),
            patch.object(front_webhook_module, "handle_email", handle_email),
        ):
            result = await front_webhook_module._process_front_webhook_event(
                payload,
                "evt_internal_forward",
                "cnv_internal_forward",
            )

        assert result == {
            "status": "ignored",
            "reason": "not inbound user message",
        }
        handle_email.assert_not_awaited()
        assert len(session.added) == 1
        assert session.added[0].event_id == "evt_internal_forward"
        assert session.commits == 1

    asyncio.run(run_case())


def test_external_sender_repairs_internal_sender_state():
    async def run_case():
        state = SimpleNamespace(sender_email="bobby@dify.ai")
        session = SimpleNamespace(
            add=lambda value: None,
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        with patch.object(
            state_tool,
            "get_state",
            AsyncMock(return_value=state),
        ):
            await state_tool.set_state(
                session,
                "cnv_internal_forward",
                "education",
                "rejected",
                "draft_created",
                {},
                sender_email="student@example.edu",
            )

        assert state.sender_email == "student@example.edu"

    asyncio.run(run_case())


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("internal forward loop tests passed")
