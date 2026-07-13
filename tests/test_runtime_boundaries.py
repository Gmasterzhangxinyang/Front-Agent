import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tool_registry import (
    ToolCallValidationError,
    ToolExecutionContext,
    prepare_llm_tool_call,
)
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


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        conversation_id="cnv_trusted",
        sender_email="customer@example.com",
    )


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


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("runtime boundary tests passed")
