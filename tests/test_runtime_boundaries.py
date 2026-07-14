import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tool_registry import (
    ToolCallValidationError,
    ToolExecutionContext,
    prepare_llm_tool_call,
)
import agent.orchestrator as orchestrator_module
import main as main_module
import tasks.scheduler as scheduler_module
import webhooks.front_webhook as front_webhook_module
from config import settings
from tools.attachments import bounded_attachments, clip_attachment_text
from tools.front import (
    AttachmentDownloadRejected,
    AttachmentTooLarge,
    get_attachment,
    read_limited_attachment,
    validate_attachment_url,
)
from webhooks.front_webhook import (
    validate_webhook_security_config,
    verify_signature,
)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        return None


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


class _InboxResponse:
    status_code = 200

    def json(self):
        return {"_results": [{"id": "inb_f9fvf"}]}


def test_billing_waiting_reply_continues_through_agent_loop():
    async def run_case():
        state = SimpleNamespace(
            category="billing",
            sub_type="invoice",
            step="awaiting_credit_note_acceptance",
            payload={"invoice_number": "INV-1"},
        )
        run_loop = AsyncMock()
        with (
            patch.object(orchestrator_module.state_tool, "get_state", AsyncMock(return_value=state)),
            patch.object(orchestrator_module, "get_conversation_messages", AsyncMock(return_value=[])),
            patch.object(orchestrator_module, "fetch_attachments_as_base64", AsyncMock(return_value=[])),
            patch.object(orchestrator_module, "fetch_attachments_as_text", AsyncMock(return_value=[])),
            patch.object(orchestrator_module, "build_case_memory_context", AsyncMock(return_value="")),
            patch.object(orchestrator_module, "_run_agent_loop", run_loop),
        ):
            await orchestrator_module.handle_email(
                "cnv_billing",
                "A supplementary Credit Note is acceptable.",
                "customer@example.com",
                [],
                object(),
            )

        run_loop.assert_awaited_once()
        prompt = run_loop.await_args.args[0][0]["content"]
        assert "Category: billing" in prompt
        assert "Step: awaiting_credit_note_acceptance" in prompt

    asyncio.run(run_case())


def test_billing_manual_review_reply_stops_before_external_or_llm_work():
    async def run_case():
        state = SimpleNamespace(
            category="billing",
            sub_type="invoice",
            step="manual_review",
            payload={"invoice_number": "INV-1"},
        )
        fetch_messages = AsyncMock()
        run_loop = AsyncMock()
        with (
            patch.object(orchestrator_module.state_tool, "get_state", AsyncMock(return_value=state)),
            patch.object(orchestrator_module, "get_conversation_messages", fetch_messages),
            patch.object(orchestrator_module, "_run_agent_loop", run_loop),
        ):
            await orchestrator_module.handle_email(
                "cnv_billing",
                "Any update?",
                "customer@example.com",
                [],
                object(),
            )

        fetch_messages.assert_not_awaited()
        run_loop.assert_not_awaited()

    asyncio.run(run_case())


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        conversation_id="cnv_trusted",
        sender_email="customer@example.com",
    )


def test_lifespan_gracefully_stops_started_scheduler():
    async def run_case():
        with (
            patch.object(main_module, "validate_webhook_security_config"),
            patch.object(main_module, "init_db", AsyncMock()),
            patch.object(main_module, "start_scheduler") as start,
            patch.object(main_module, "stop_scheduler", AsyncMock()) as stop,
            patch.object(settings, "enable_scheduler", True),
        ):
            async with main_module.lifespan(main_module.app):
                pass

        start.assert_called_once_with()
        stop.assert_awaited_once_with()

    asyncio.run(run_case())


def test_stop_scheduler_waits_for_real_asyncio_job():
    async def run_case():
        started = asyncio.Event()
        release = asyncio.Event()
        finished = False
        cancelled = False
        isolated_scheduler = AsyncIOScheduler()

        @scheduler_module._track_scheduler_job
        async def slow_job():
            nonlocal finished, cancelled
            started.set()
            try:
                await release.wait()
                finished = True
            except asyncio.CancelledError:
                cancelled = True
                raise

        with patch.object(scheduler_module, "scheduler", isolated_scheduler):
            isolated_scheduler.add_job(slow_job, "date")
            isolated_scheduler.start()
            await asyncio.wait_for(started.wait(), timeout=1)

            stopping = asyncio.create_task(scheduler_module.stop_scheduler())
            await asyncio.sleep(0)
            assert not stopping.done()
            assert not cancelled

            release.set()
            await asyncio.wait_for(stopping, timeout=1)

        assert finished
        assert not cancelled
        assert not isolated_scheduler.running

    asyncio.run(run_case())


def test_llm_tool_context_overrides_conversation_id():
    prepared = prepare_llm_tool_call(
        "front_create_draft",
        {
            "conversation_id": "cnv_attacker",
            "body": "Safe draft",
            "category": "technical/how_to",
            "reason_cn": "docs guidance",
        },
        _context(),
    )

    assert prepared["conversation_id"] == "cnv_trusted"
    assert prepared["to_email"] == "customer@example.com"


def test_llm_tool_rejects_model_supplied_recipient():
    try:
        prepare_llm_tool_call(
            "front_create_draft",
            {
                "conversation_id": "cnv_trusted",
                "body": "Unsafe draft",
                "category": "technical/how_to",
                "reason_cn": "docs guidance",
                "to_email": "attacker@example.net",
            },
            _context(),
        )
    except ToolCallValidationError as exc:
        assert "unknown arguments: to_email" in str(exc)
    else:
        raise AssertionError("model-supplied to_email must be rejected")


def test_llm_tool_rejects_missing_arguments():
    try:
        prepare_llm_tool_call(
            "front_create_draft",
            {"conversation_id": "cnv_trusted", "body": "Missing fields"},
            _context(),
        )
    except ToolCallValidationError as exc:
        assert "missing required arguments" in str(exc)
    else:
        raise AssertionError("missing required arguments must be rejected")


def test_llm_tool_rejects_unknown_arguments():
    try:
        prepare_llm_tool_call(
            "front_add_comment",
            {
                "conversation_id": "cnv_trusted",
                "body": "Comment",
                "extra": "not allowed",
            },
            _context(),
        )
    except ToolCallValidationError as exc:
        assert "unknown arguments: extra" in str(exc)
    else:
        raise AssertionError("unknown arguments must be rejected")


def test_llm_tool_rejects_invalid_enum_values():
    try:
        prepare_llm_tool_call(
            "front_forward_to_community",
            {
                "conversation_id": "cnv_trusted",
                "summary": "Summary",
                "region": "moon",
            },
            _context(),
        )
    except ToolCallValidationError as exc:
        assert "invalid enum value for region" in str(exc)
    else:
        raise AssertionError("invalid enum values must be rejected")


def test_llm_tool_rejects_invalid_argument_types():
    try:
        prepare_llm_tool_call(
            "front_add_comment",
            {
                "conversation_id": "cnv_trusted",
                "body": {"not": "a string"},
            },
            _context(),
        )
    except ToolCallValidationError as exc:
        assert "invalid type for body: expected string" in str(exc)
    else:
        raise AssertionError("invalid argument types must be rejected")


def test_unsigned_webhooks_fail_closed_by_default():
    with (
        patch.object(settings, "front_webhook_secret", ""),
        patch.object(settings, "allow_unsigned_front_webhooks", False),
    ):
        assert not verify_signature(b"{}", "")
        try:
            validate_webhook_security_config()
        except RuntimeError as exc:
            assert "FRONT_WEBHOOK_SECRET" in str(exc)
        else:
            raise AssertionError("missing webhook secret must fail startup")


def test_unsigned_webhooks_require_explicit_local_override():
    with (
        patch.object(settings, "front_webhook_secret", ""),
        patch.object(settings, "allow_unsigned_front_webhooks", True),
        patch("webhooks.front_webhook.logger.warning") as warning,
    ):
        validate_webhook_security_config()
        assert verify_signature(b"{}", "")
        warning.assert_called_once()


def test_attachment_url_requires_https_and_exact_allowed_host():
    with patch.object(
        settings,
        "front_attachment_allowed_hosts",
        "api2.frontapp.com,files.frontapp.com",
    ):
        url = "https://api2.frontapp.com/download/attachment"
        assert validate_attachment_url(url) == url

        rejected = [
            "http://api2.frontapp.com/download/attachment",
            "https://api2.frontapp.com.evil.test/attachment",
            "https://user:pass@api2.frontapp.com/attachment",
            "https://api2.frontapp.com:8443/attachment",
        ]
        for unsafe_url in rejected:
            try:
                validate_attachment_url(unsafe_url)
            except AttachmentDownloadRejected:
                pass
            else:
                raise AssertionError(
                    f"unsafe attachment URL accepted: {unsafe_url}"
                )


def test_rejected_attachment_url_does_not_create_http_client():
    async def run_case():
        with (
            patch.object(
                settings,
                "front_attachment_allowed_hosts",
                "api2.frontapp.com",
            ),
            patch("tools.front.httpx.AsyncClient") as client,
        ):
            try:
                await get_attachment("https://attacker.example/file")
            except AttachmentDownloadRejected:
                pass
            else:
                raise AssertionError("unapproved attachment host was accepted")
            client.assert_not_called()

    asyncio.run(run_case())


def test_attachment_size_is_enforced_from_header_and_stream():
    request = httpx.Request("GET", "https://api2.frontapp.com/file")
    declared = httpx.Response(
        200,
        headers={"Content-Length": "11"},
        content=b"",
        request=request,
    )
    try:
        asyncio.run(read_limited_attachment(declared, max_bytes=10))
    except AttachmentTooLarge:
        pass
    else:
        raise AssertionError("oversized Content-Length must be rejected")

    streamed = httpx.Response(
        200,
        stream=_ChunkStream([b"123456", b"78901"]),
        request=request,
    )
    try:
        asyncio.run(read_limited_attachment(streamed, max_bytes=10))
    except AttachmentTooLarge:
        pass
    else:
        raise AssertionError("oversized streamed body must be rejected")


def test_attachment_count_and_text_limits_are_deterministic():
    attachments = [{"filename": str(index)} for index in range(7)]
    with (
        patch.object(settings, "max_attachment_count", 5),
        patch.object(settings, "max_attachment_text_chars", 8),
        patch("tools.attachments.logger.warning") as warning,
    ):
        assert len(bounded_attachments(attachments)) == 5
        assert clip_attachment_text("1234567890") == "12345678"
        warning.assert_called_once()


def test_only_failed_review_state_reenters_initial_flow():
    assert orchestrator_module.is_failed_retry_state(
        SimpleNamespace(step="failed_needs_review")
    )
    assert not orchestrator_module.is_failed_retry_state(
        SimpleNamespace(step="waiting_for_user")
    )
    assert not orchestrator_module.is_failed_retry_state(None)


def test_handler_failure_is_not_acknowledged_or_recorded():
    async def run_case():
        session = _FakeSession()
        handle_email = AsyncMock(side_effect=RuntimeError("temporary failure"))
        execute_tool_call = AsyncMock(return_value="forwarded")

        payload = {
            "target": {
                "data": {
                    "text": "hello",
                    "from": {"handle": "customer@example.com"},
                }
            }
        }

        with (
            patch.object(
                front_webhook_module,
                "AsyncSessionLocal",
                lambda: session,
            ),
            patch.object(front_webhook_module, "handle_email", handle_email),
            patch.object(front_webhook_module.logger, "error"),
            patch("tools.front.front_request", AsyncMock(return_value=_InboxResponse())),
            patch("tools.front.reopen_conversation", AsyncMock(return_value=True)),
            patch("tools.state.set_state", AsyncMock()),
            patch("tools.handoff.forward_to_bobby", AsyncMock()),
            patch("agent.tool_registry.execute_tool_call", execute_tool_call),
        ):
            try:
                await front_webhook_module._process_front_webhook_event(
                    payload,
                    "evt_retryable",
                    "cnv_retryable",
                )
            except HTTPException as exc:
                assert exc.status_code == 503
                assert exc.detail == "handler_error"
            else:
                raise AssertionError("handler failures must not return success")

        assert session.added == []
        execute_tool_call.assert_awaited_once_with(
            "front_forward_to_bobby",
            {
                "message": (
                    "❌ 邮件处理出错！对话ID: cnv_retryable, "
                    "错误: temporary failure"
                ),
                "conversation_id": "cnv_retryable",
            },
            session,
        )

    asyncio.run(run_case())


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("runtime boundary tests passed")
