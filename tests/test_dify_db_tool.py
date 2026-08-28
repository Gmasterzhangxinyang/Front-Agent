import asyncio
import json
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
from tools import dify_billing


def test_gateway_psql_footer_is_not_treated_as_a_database_row():
    payload = {
        "result": {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "success": True,
                    "csv": "account_id,email\n(0 rows)\n",
                    "truncated": False,
                }),
            }],
            "isError": False,
        }
    }
    assert dify_billing._gateway_rows(payload) == []


def test_billing_lookup_rebinds_trusted_sender_and_conversation():
    prepared = prepare_llm_tool_call(
        "dify_lookup_billing",
        {"conversation_id": "model-chosen"},
        ToolExecutionContext(
            conversation_id="cnv_trusted",
            sender_email="customer@example.com",
        ),
    )

    assert prepared == {
        "conversation_id": "cnv_trusted",
        "sender_email": "customer@example.com",
    }


def test_billing_lookup_rejects_model_supplied_email_or_sql():
    for extra in (
        {"email": "someone-else@example.com"},
        {"sql": "SELECT 1"},
        {"scope": "all"},
    ):
        try:
            prepare_llm_tool_call(
                "dify_lookup_billing",
                {"conversation_id": "cnv_test", **extra},
                ToolExecutionContext(conversation_id="cnv_test"),
            )
        except ToolCallValidationError as exc:
            assert "unknown arguments" in str(exc)
        else:
            raise AssertionError(f"unsafe arguments were accepted: {extra}")


def test_unconfigured_billing_lookup_fails_closed_without_network():
    async def run_case():
        with patch.object(settings, "dify_db_mcp_token", ""):
            return await dify_billing.lookup_billing(
                "customer@example.com",
                "cnv_test",
            )

    result = asyncio.run(run_case())
    assert result["status"] == "not_configured"


def test_billing_lookup_uses_only_prod_identity_and_billing_data():
    queries = []

    class FakeSession:
        def __init__(self, url, token, timeout_seconds):
            assert url == "https://gateway.example/mcp"
            assert token == "secret"
            assert timeout_seconds == 4.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def query(self, database, sql, ticket_id):
            queries.append((database, sql, ticket_id))
            if database == "prod":
                return [{
                    "account_id": "0dfed0ac-e13d-4abc-8f93-520fb9d98784",
                    "email": "customer@example.com",
                    "account_status": "active",
                    "tenant_id": "77c11e22-6023-4569-a002-b969f2a20f86",
                    "workspace_name": "Example",
                    "workspace_plan": "professional",
                }]
            if "account_deletion_logs" in sql:
                return []
            if "tenant_subscription_settings" in sql:
                return [{"plan": "professional", "subscription_status": "active"}]
            if "tenant_feature_usages" in sql:
                return [{"feature_key": "messages", "quota": "5000", "usage": "20"}]
            raise AssertionError(f"unexpected query: {database} {sql}")

    async def run_case():
        with (
            patch.object(settings, "dify_db_mcp_url", "https://gateway.example/mcp"),
            patch.object(settings, "dify_db_mcp_token", "secret"),
            patch.object(settings, "dify_db_mcp_timeout_seconds", 4.0),
            patch.object(dify_billing, "_McpSession", FakeSession),
        ):
            return await dify_billing.lookup_billing(
                "customer@example.com",
                "cnv_audit",
            )

    result = asyncio.run(run_case())
    assert result["status"] == "ok"
    assert result["found"] is True
    assert result["subscriptions"][0]["subscription_status"] == "active"
    assert result["feature_usage"][0]["usage"] == "20"
    assert {database for database, _, _ in queries} == {"prod", "billing"}
    assert all(ticket_id == "cnv_audit" for _, _, ticket_id in queries)


def test_sql_literal_escapes_quotes():
    assert dify_billing._sql_literal("o'hara@example.com") == "'o''hara@example.com'"


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
