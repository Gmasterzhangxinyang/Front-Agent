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
    _action_identity,
    prepare_llm_tool_call,
)
import agent.orchestrator as orchestrator_module
import main as main_module
import tasks.scheduler as scheduler_module
import webhooks.front_webhook as front_webhook_module
from agent.routing import EDUCATION_ACCOUNT_SUSPENSION_DRAFT
from config import settings
from tools.attachments import bounded_attachments, clip_attachment_text
from tools.front import (
    AttachmentDownloadRejected,
    AttachmentTooLarge,
    create_draft,
    get_attachment,
    markdown_to_safe_html,
    read_limited_attachment,
    reply_to_conversation,
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


class _FrontResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}
        self.text = ""

    def json(self):
        return self.payload


def test_front_email_markdown_is_rendered_as_safe_html():
    result = markdown_to_safe_html(
        "Options:\n"
        "- **Free Sandbox plan**: Start at no cost.\n"
        "- [Education discount](https://dify.ai/pricing#education)\n"
        "More details are available above.\n\n"
        "<script>alert('unsafe')</script>\n\n"
        "[Unsafe link](javascript:alert('unsafe'))"
    )

    assert "<ul>" in result
    assert "<strong>Free Sandbox plan</strong>" in result
    assert '<a href="https://dify.ai/pricing#education"' in result
    assert 'target="_blank"' in result
    assert "script" not in result
    assert "javascript:" not in result


def test_front_draft_payload_uses_rendered_markdown_html():
    async def run_case():
        request = AsyncMock(
            side_effect=[
                _FrontResponse(
                    payload={
                        "_results": [
                            {"send_as": "support@dify.ai"},
                        ]
                    }
                ),
                _FrontResponse(status_code=200),
            ]
        )
        with (
            patch(
                "tools.front.get_conversation",
                AsyncMock(
                    return_value={
                        "recipient": {"handle": "customer@example.com"}
                    }
                ),
            ),
            patch("tools.front.front_request", request),
        ):
            assert await create_draft(
                "cnv_markdown",
                "Hello\n- **First**\n- **Second**",
            )

        payload = request.await_args_list[1].kwargs["json"]
        assert payload["body"] == (
            "<p>Hello</p>\n<ul>\n<li><strong>First</strong></li>\n"
            "<li><strong>Second</strong></li>\n</ul>"
        )
        assert payload["should_add_default_signature"] is True

    asyncio.run(run_case())


def test_front_direct_reply_payload_uses_default_signature():
    async def run_case():
        request = AsyncMock(
            side_effect=[
                _FrontResponse(
                    payload={
                        "_results": [
                            {"send_as": "support@dify.ai"},
                        ]
                    }
                ),
                _FrontResponse(status_code=202),
            ]
        )
        with (
            patch(
                "tools.front.get_conversation",
                AsyncMock(
                    return_value={
                        "recipient": {"handle": "customer@example.com"}
                    }
                ),
            ),
            patch("tools.front.front_request", request),
        ):
            assert await reply_to_conversation("cnv_reply", "Hello")

        payload = request.await_args_list[1].kwargs["json"]
        assert payload["should_add_default_signature"] is True

    asyncio.run(run_case())


def test_only_waiting_invoice_credit_note_reply_continues_billing_flow():
    async def run_case(state, should_continue):
        run_loop = AsyncMock()
        fetch_messages = AsyncMock(return_value=[])
        linked_history = [
            {
                "conversation_id": "cnv_other_thread",
                "subject": "Earlier billing question",
                "category": "billing",
                "sub_type": "invoice",
                "step": "draft_created",
                "payload": {},
                "transcript": "[User]: This is the earlier invoice context.",
            }
        ]
        load_history = AsyncMock(return_value=linked_history)
        db = object()
        with (
            patch.object(orchestrator_module.state_tool, "get_state", AsyncMock(return_value=state)),
            patch.object(
                orchestrator_module,
                "_load_linked_conversation_history",
                load_history,
            ),
            patch.object(orchestrator_module, "get_conversation_messages", fetch_messages),
            patch.object(orchestrator_module, "fetch_attachments_as_base64", AsyncMock(return_value=[])),
            patch.object(orchestrator_module, "fetch_attachments_as_text", AsyncMock(return_value=[])),
            patch.object(orchestrator_module, "build_case_memory_context", AsyncMock(return_value="")),
            patch.object(orchestrator_module, "_run_agent_loop", run_loop),
        ):
            await orchestrator_module.handle_email(
                "cnv_billing",
                "Yes, please provide the Credit Note.",
                "customer@example.com",
                [],
                db,
            )

        load_history.assert_awaited_once_with(
            db,
            "customer@example.com",
            "cnv_billing",
            days=30,
            limit=5,
        )
        if should_continue:
            fetch_messages.assert_awaited_once()
            run_loop.assert_awaited_once()
            prompt = run_loop.await_args.args[0][0]["content"]
            assert "Step: awaiting_credit_note_confirmation" in prompt
            assert "cnv_other_thread" in prompt
            assert "This is the earlier invoice context." in prompt
        else:
            fetch_messages.assert_not_awaited()
            run_loop.assert_not_awaited()

    waiting = SimpleNamespace(
        category="billing",
        sub_type="invoice",
        step="awaiting_credit_note_confirmation",
        payload={"invoice": "#0NOROUBA-0001"},
    )
    completed = SimpleNamespace(
        category="billing",
        sub_type="invoice",
        step="credit_note_requested",
        payload={"invoice": "#0NOROUBA-0001"},
    )
    asyncio.run(run_case(waiting, True))
    asyncio.run(run_case(completed, False))


def test_front_internal_comments_have_content_level_deduplication():
    first = _action_identity(
        "front_add_comment",
        {"conversation_id": "cnv_billing", "body": "Credit Note requested"},
    )
    same = _action_identity(
        "front_add_comment",
        {"conversation_id": "cnv_billing", "body": "  Credit   Note requested  "},
    )
    different = _action_identity(
        "front_add_comment",
        {"conversation_id": "cnv_billing", "body": "Different comment"},
    )

    assert first is not None
    assert first == same
    assert first != different


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


def test_llm_customer_draft_rejects_manual_body_signoff():
    try:
        prepare_llm_tool_call(
            "front_create_draft",
            {
                "conversation_id": "cnv_trusted",
                "body": "English answer.\n\nBest regards,\nDify Support Team",
                "category": "technical/how_to",
                "reason_cn": "docs guidance",
            },
            ToolExecutionContext(
                conversation_id="cnv_trusted",
                sender_email="customer@example.com",
                original_message="How do I configure this?",
            ),
        )
    except ToolCallValidationError as exc:
        assert "must not include a manual sign-off" in str(exc)
    else:
        raise AssertionError("SaaS customer drafts must leave the body unsigned")

    prepared = prepare_llm_tool_call(
        "front_create_draft",
        {
            "conversation_id": "cnv_trusted",
            "body": "English answer without a manual sign-off.",
            "category": "technical/how_to",
            "reason_cn": "docs guidance",
        },
        ToolExecutionContext(
            conversation_id="cnv_trusted",
            sender_email="customer@example.com",
            original_message="How do I configure this?",
        ),
    )
    assert prepared["body"] == "English answer without a manual sign-off."


def test_llm_non_english_customer_draft_requires_english_first_bilingual_structure():
    context = ToolExecutionContext(
        conversation_id="cnv_trusted",
        sender_email="customer@example.com",
        original_message="您好，我想了解如何配置这个工作流并解决当前遇到的问题。",
    )
    try:
        prepare_llm_tool_call(
            "front_create_draft",
            {
                "conversation_id": "cnv_trusted",
                "body": "English only.",
                "category": "technical/how_to",
                "reason_cn": "missing translation",
            },
            context,
        )
    except ToolCallValidationError as exc:
        assert "required reference-translation notice" in str(exc)
    else:
        raise AssertionError("non-English customer drafts must include a reference translation")


    body = (
        "Hello, here is the requested guidance.\n\n"
        "For reference, a Chinese translation is provided below.\n\n"
        "您好，以下是您需要的操作说明。"
    )
    prepared = prepare_llm_tool_call(
        "front_create_draft",
        {
            "conversation_id": "cnv_trusted",
            "body": body,
            "category": "technical/how_to",
            "reason_cn": "双语说明",
        },
        context,
    )

    assert prepared["body"] == body


def _mainland_china_vat_invoice_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        conversation_id="cnv_vat",
        sender_email="student@example.edu",
        original_message=(
            "I am a student in China. Can you issue a Chinese VAT invoice "
            "for university reimbursement?"
        ),
    )


def _vat_invoice_tool_args(body: str) -> dict:
    return {
        "conversation_id": "cnv_vat",
        "body": body,
        "category": "billing/invoice",
        "reason_cn": "中国增值税发票政策说明",
    }


def test_mainland_china_vat_invoice_draft_requires_capability_reimbursement_boundary_and_next_step():
    weak_body = (
        "Hi,\n\n"
        "Please note that LangGenius is a non-PRC entity. Therefore, we "
        "cannot issue a VAT invoice. For reimbursement purposes, please use "
        "the commercial invoice."
    )
    try:
        prepare_llm_tool_call(
            "front_create_draft",
            _vat_invoice_tool_args(weak_body),
            _mainland_china_vat_invoice_context(),
        )
    except ToolCallValidationError as exc:
        assert "actual invoicing capability" in str(exc)
    else:
        raise AssertionError("weak VAT invoice wording must be rejected")

    approved_body = (
        "Hi Yujie,\n\n"
        "Thank you for reaching out and for providing the payment details.\n\n"
        "LangGenius, Inc. is not a PRC-registered invoicing entity and does "
        "not issue invoices through the PRC tax administration system. "
        "Therefore, we're unable to provide a Chinese VAT invoice, including "
        "either a special VAT invoice or a general VAT invoice.\n\n"
        "The invoice and receipt you have already received are the official "
        "commercial billing documents issued by LangGenius, Inc. for this "
        "transaction. Whether these documents can be accepted for "
        "reimbursement is subject to your institution's reimbursement "
        "policies.\n\n"
        "If your institution requires additional billing information or "
        "supporting documentation, please share the specific requirements "
        "and we can check what we're able to provide."
    )
    prepared = prepare_llm_tool_call(
        "front_create_draft",
        _vat_invoice_tool_args(approved_body),
        _mainland_china_vat_invoice_context(),
    )
    assert prepared["body"] == approved_body


def test_mainland_china_vat_invoice_guard_is_scoped_to_matching_invoice_requests():
    ordinary_invoice = prepare_llm_tool_call(
        "front_create_draft",
        {
            "conversation_id": "cnv_invoice",
            "body": "Please use the Billing Portal.",
            "category": "billing/invoice",
            "reason_cn": "普通账单信息更新",
        },
        ToolExecutionContext(
            conversation_id="cnv_invoice",
            sender_email="customer@example.com",
            original_message="Where can I update my company address on future invoices?",
        ),
    )
    assert ordinary_invoice["conversation_id"] == "cnv_invoice"

    unrelated_category = prepare_llm_tool_call(
        "front_create_draft",
        {
            "conversation_id": "cnv_purchase",
            "body": "Here is the plan information.",
            "category": "purchase/pro",
            "reason_cn": "套餐说明",
        },
        ToolExecutionContext(
            conversation_id="cnv_purchase",
            sender_email="customer@example.com",
            original_message="Does your plan include VAT invoice support in China?",
        ),
    )
    assert unrelated_category["conversation_id"] == "cnv_purchase"


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


def test_account_suspension_draft_preserves_english_and_appends_translation():
    english_draft = orchestrator_module._format_account_suspension_draft()
    assert english_draft == EDUCATION_ACCOUNT_SUSPENSION_DRAFT

    translated_draft = orchestrator_module._format_account_suspension_draft(
        "Chinese",
        "您好，这是对应的中文参考版本。",
    )
    assert translated_draft.startswith(f"{english_draft}\n\n")
    assert (
        "For reference, a Chinese translation is provided below.\n\n"
        "您好，这是对应的中文参考版本。"
    ) in translated_draft
    assert "Dify Support Team" not in translated_draft
    assert "Best regards" not in translated_draft


def test_account_suspension_builder_uses_detected_customer_language():
    async def run_case():
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"is_english": false, "language": "Spanish", '
                            '"translation": "Hola, esta es la traducción aprobada."}'
                        )
                    )
                )
            ]
        )
        create = AsyncMock(return_value=response)
        with patch.object(
            orchestrator_module.client.chat.completions,
            "create",
            create,
        ):
            draft = await orchestrator_module._build_account_suspension_draft(
                "Mi cuenta está suspendida. ¿Pueden revisarla?"
            )

        assert draft.startswith(EDUCATION_ACCOUNT_SUSPENSION_DRAFT)
        assert "For reference, a Spanish translation is provided below." in draft
        assert "Hola, esta es la traducción aprobada." in draft
        assert "Dify Support Team" not in draft
        assert "Best regards" not in draft
        create.assert_awaited_once()

    asyncio.run(run_case())



def test_linked_history_loads_sent_transcript_and_excludes_drafts():
    async def run_case():
        db = object()
        history = [
            {
                "conversation_id": "cnv_prior",
                "category": "education",
                "sub_type": "rejected",
                "step": "forwarded_keep_open",
                "payload": {"linear_url": "https://linear.app/dify/issue/CUS-1513"},
                "created_at": "2026-08-11T01:00:00",
            }
        ]
        messages = [
            {
                "type": "email",
                "is_inbound": True,
                "is_draft": False,
                "text": "我的学生账号被误封了，学生证已附上。",
            },
            {
                "type": "email",
                "is_inbound": False,
                "is_draft": True,
                "text": "UNSENT DUPLICATE DRAFT",
                "recipients": [{"role": "to", "handle": "student@example.edu"}],
            },
            {
                "type": "email",
                "is_inbound": False,
                "is_draft": False,
                "text": "We reviewed the suspension.",
                "recipients": [{"role": "to", "handle": "student@example.edu"}],
            },
        ]
        get_history = AsyncMock(return_value=history)
        get_conversations = AsyncMock(
            return_value=[
                {"id": "cnv_current", "subject": "Current"},
                {
                    "id": "cnv_prior",
                    "subject": "Earlier suspension appeal",
                    "status_category": "open",
                },
            ]
        )
        get_messages = AsyncMock(return_value=messages)

        with (
            patch.object(orchestrator_module.state_tool, "get_user_history", get_history),
            patch.object(
                orchestrator_module,
                "get_contact_conversations",
                get_conversations,
            ),
            patch.object(
                orchestrator_module,
                "get_conversation_messages",
                get_messages,
            ),
        ):
            linked = await orchestrator_module._load_linked_conversation_history(
                db,
                " Student@Example.edu ",
                "cnv_current",
            )

        get_history.assert_awaited_once_with(
            db,
            " Student@Example.edu ",
            days=30,
            exclude_conversation_id="cnv_current",
            limit=5,
        )
        get_conversations.assert_awaited_once_with(
            " Student@Example.edu ",
            limit=10,
        )
        assert linked[0]["subject"] == "Earlier suspension appeal"
        assert linked[0]["history_source"] == "front+state"
        assert linked[0]["has_sent_customer_reply"] is True
        assert "我的学生账号被误封了" in linked[0]["transcript"]
        assert "We reviewed the suspension." in linked[0]["transcript"]
        assert "UNSENT DUPLICATE DRAFT" not in linked[0]["transcript"]

    asyncio.run(run_case())


def test_linked_history_includes_front_threads_without_local_state():
    async def run_case():
        get_history = AsyncMock(return_value=[])
        get_conversations = AsyncMock(
            return_value=[
                {"id": "cnv_current", "subject": "Current thread"},
                {
                    "id": "cnv_untracked",
                    "subject": "Earlier untracked question",
                    "status_category": "resolved",
                    "created_at": 1786400000,
                },
            ]
        )
        get_messages = AsyncMock(
            return_value=[
                {
                    "type": "email",
                    "is_inbound": True,
                    "is_draft": False,
                    "text": "My account was banned; the relevant facts are in this thread.",
                }
            ]
        )

        with (
            patch.object(orchestrator_module.state_tool, "get_user_history", get_history),
            patch.object(
                orchestrator_module,
                "get_contact_conversations",
                get_conversations,
            ),
            patch.object(
                orchestrator_module,
                "get_conversation_messages",
                get_messages,
            ),
        ):
            linked = await orchestrator_module._load_linked_conversation_history(
                object(),
                "person@example.com",
                "cnv_current",
            )

        assert len(linked) == 1
        assert linked[0]["conversation_id"] == "cnv_untracked"
        assert linked[0].get("category") is None
        assert linked[0]["history_source"] == "front"
        assert "relevant facts" in linked[0]["transcript"]
        assert orchestrator_module._linked_suspension_cases(linked) == linked

    asyncio.run(run_case())


def test_cross_conversation_suspension_followup_suppresses_duplicate_draft():
    async def run_case():
        linked = [
            {
                "conversation_id": "cnv_prior",
                "category": "education",
                "sub_type": "rejected",
                "step": "forwarded_keep_open",
                "payload": {
                    "linear_url": "https://linear.app/dify/issue/CUS-1513",
                    "summary": "学生账号被误封，已提供学生证。",
                },
                "created_at": "2026-08-11T01:00:00",
                "transcript": (
                    "[User]: 我的教育版账号被误封了，学生证已提供。\n\n"
                    "[Support]: Your account will therefore remain suspended."
                ),
                "has_sent_customer_reply": True,
            }
        ]
        load_linked = AsyncMock(return_value=linked)
        execute_tool = AsyncMock(return_value="comment_added")
        set_state = AsyncMock()
        build_draft = AsyncMock()
        execute_route = AsyncMock()

        with (
            patch.object(
                orchestrator_module.state_tool,
                "get_state",
                AsyncMock(return_value=None),
            ),
            patch.object(
                orchestrator_module,
                "_load_linked_conversation_history",
                load_linked,
            ),
            patch.object(orchestrator_module, "execute_tool_call", execute_tool),
            patch.object(orchestrator_module.state_tool, "set_state", set_state),
            patch.object(
                orchestrator_module,
                "_build_account_suspension_draft",
                build_draft,
            ),
            patch.object(
                orchestrator_module,
                "_execute_initial_route",
                execute_route,
            ),
        ):
            await orchestrator_module.handle_email(
                "cnv_followup",
                "我上一封已经提交学生证，为什么又发同样的封禁邮件？",
                "student@example.edu",
                [],
                object(),
                message_subject="我的教育版账号被误封了",
            )

        load_linked.assert_awaited_once()
        assert [call.args[0] for call in execute_tool.await_args_list] == [
            "front_add_comment",
            "front_add_comment",
        ]
        assert execute_tool.await_args_list[0].args[1]["conversation_id"] == "cnv_followup"
        assert execute_tool.await_args_list[1].args[1]["conversation_id"] == "cnv_prior"
        state_args = set_state.await_args.args
        assert state_args[1:5] == (
            "cnv_followup",
            "education",
            "account_suspended",
            "manual_review",
        )
        assert state_args[5]["canonical_conversation_id"] == "cnv_prior"
        assert state_args[5]["linear_urls"] == [
            "https://linear.app/dify/issue/CUS-1513"
        ]
        build_draft.assert_not_awaited()
        execute_route.assert_not_awaited()

    asyncio.run(run_case())



def test_model_classified_cross_thread_followup_uses_linked_context_before_routing():
    async def run_case():
        linked = [
            {
                "conversation_id": "cnv_prior",
                "category": "education",
                "sub_type": "rejected",
                "step": "forwarded_keep_open",
                "payload": {
                    "linear_url": "https://linear.app/dify/issue/CUS-1513",
                    "summary": "学生账号被误封，已提供学生证。",
                },
                "created_at": "2026-08-11T01:00:00",
                "transcript": "[User]: 我的教育版账号被误封了，学生证已提供。",
                "has_sent_customer_reply": True,
            }
        ]
        classification = orchestrator_module.ClassificationResult(
            category="education",
            sub_type="account_suspended",
            sender_email="student@example.edu",
            summary="User is following up on the earlier suspension appeal.",
            confidence=0.98,
        )
        classify = AsyncMock(return_value=classification)
        execute_tool = AsyncMock(return_value="comment_added")
        set_state = AsyncMock()
        execute_route = AsyncMock()
        run_loop = AsyncMock()

        with (
            patch.object(
                orchestrator_module.state_tool,
                "get_state",
                AsyncMock(return_value=None),
            ),
            patch.object(
                orchestrator_module,
                "_load_linked_conversation_history",
                AsyncMock(return_value=linked),
            ),
            patch.object(
                orchestrator_module,
                "get_conversation_messages",
                AsyncMock(
                    return_value=[
                        {
                            "type": "email",
                            "is_inbound": True,
                            "is_draft": False,
                            "text": "我上一封已经提交材料，为什么又发一样的邮件？",
                        }
                    ]
                ),
            ),
            patch.object(
                orchestrator_module,
                "fetch_attachments_as_base64",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                orchestrator_module,
                "fetch_attachments_as_text",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                orchestrator_module,
                "build_case_memory_context",
                AsyncMock(return_value=""),
            ),
            patch.object(orchestrator_module, "_classify", classify),
            patch.object(orchestrator_module, "execute_tool_call", execute_tool),
            patch.object(orchestrator_module.state_tool, "set_state", set_state),
            patch.object(
                orchestrator_module,
                "_execute_initial_route",
                execute_route,
            ),
            patch.object(orchestrator_module, "_run_agent_loop", run_loop),
        ):
            await orchestrator_module.handle_email(
                "cnv_followup",
                "我上一封已经提交材料，为什么又发一样的邮件？",
                "student@example.edu",
                [],
                object(),
                message_subject="我要求审查你们没看到吗？",
            )

        assert "cnv_prior" in classify.await_args.kwargs["case_memory_context"]
        assert "我的教育版账号被误封了" in classify.await_args.kwargs[
            "case_memory_context"
        ]
        assert execute_tool.await_args_list[0].args[0] == "front_add_comment"
        assert set_state.await_args.args[4] == "manual_review"
        execute_route.assert_not_awaited()
        run_loop.assert_not_awaited()

    asyncio.run(run_case())

def test_subject_only_account_suspension_uses_standard_draft_route():
    async def run_case():
        execute_route = AsyncMock()
        fetch_messages = AsyncMock()
        localized_draft = orchestrator_module._format_account_suspension_draft(
            "Chinese",
            "您好，这是对应的中文参考版本。",
        )
        build_draft = AsyncMock(return_value=localized_draft)

        with (
            patch.object(
                orchestrator_module.state_tool,
                "get_state",
                AsyncMock(return_value=None),
            ),
            patch.object(
                orchestrator_module,
                "_load_linked_conversation_history",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                orchestrator_module,
                "_execute_initial_route",
                execute_route,
            ),
            patch.object(
                orchestrator_module,
                "_build_account_suspension_draft",
                build_draft,
            ),
            patch.object(
                orchestrator_module,
                "get_conversation_messages",
                fetch_messages,
            ),
        ):
            await orchestrator_module.handle_email(
                "cnv_subject_ban",
                "邮箱和学生证信息见正文。",
                "student@example.edu",
                [],
                object(),
                message_subject="我的个人学生账号被误封了",
            )

        route = execute_route.await_args.args[0]
        assert route.name == "account_suspension_draft"
        assert route.tool_args["body"] == localized_draft
        build_draft.assert_awaited_once_with(
            "Subject: 我的个人学生账号被误封了\n\n邮箱和学生证信息见正文。"
        )
        fetch_messages.assert_not_awaited()

    asyncio.run(run_case())


def test_front_webhook_passes_message_subject_to_handler():
    async def run_case():
        session = _FakeSession()
        handle_email = AsyncMock()
        payload = {
            "target": {
                "data": {
                    "subject": "My account was suspended",
                    "text": "Please review the attached information.",
                    "from": {"handle": "customer@example.com"},
                }
            }
        }

        with (
            patch.object(front_webhook_module, "AsyncSessionLocal", lambda: session),
            patch.object(front_webhook_module, "handle_email", handle_email),
            patch("tools.front.front_request", AsyncMock(return_value=_InboxResponse())),
        ):
            result = await front_webhook_module._process_front_webhook_event(
                payload,
                "evt_subject",
                "cnv_subject",
            )

        assert result == {"status": "ok"}
        assert handle_email.await_args.kwargs["message_subject"] == (
            "My account was suspended"
        )

    asyncio.run(run_case())


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
