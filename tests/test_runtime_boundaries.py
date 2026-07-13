import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tool_registry import (
    ToolCallValidationError,
    ToolExecutionContext,
    prepare_llm_tool_call,
)
from config import settings
from webhooks.front_webhook import (
    validate_webhook_security_config,
    verify_signature,
)


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


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("runtime boundary tests passed")
