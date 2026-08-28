import csv
import io
import json
import re
import uuid
from typing import Any

import httpx


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MCP_PROTOCOL_VERSION = "2025-03-26"


class BillingGatewayError(RuntimeError):
    pass


def _normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 320 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("invalid customer email")
    return email


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _decode_response(response: httpx.Response) -> dict[str, Any] | None:
    if not response.content:
        return None
    if "text/event-stream" not in response.headers.get("content-type", ""):
        return response.json()

    payload = None
    for line in response.text.splitlines():
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
    return payload


def _gateway_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    if payload.get("error"):
        raise BillingGatewayError(str(payload["error"]))

    result = payload.get("result") or {}
    content = result.get("content") or []
    text_block = next(
        (item.get("text") for item in content if item.get("type") == "text"),
        None,
    )
    if not text_block:
        raise BillingGatewayError("DB Gateway returned no query result")
    try:
        gateway_result = json.loads(text_block)
    except json.JSONDecodeError as exc:
        raise BillingGatewayError("DB Gateway returned malformed query data") from exc
    if result.get("isError") or not gateway_result.get("success"):
        error = gateway_result.get("error") or gateway_result.get("code") or "query failed"
        raise BillingGatewayError(str(error))
    if gateway_result.get("truncated"):
        raise BillingGatewayError("DB Gateway truncated a bounded billing query")

    csv_text = gateway_result.get("csv") or ""
    if not csv_text.strip():
        return []

    rows = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        values = list(row.values())
        first_value = (values[0] or "").strip() if values else ""
        other_values_empty = all(not (value or "").strip() for value in values[1:])
        if re.fullmatch(r"\(\d+ rows?\)", first_value) and other_values_empty:
            continue
        rows.append(dict(row))
    return rows


class _McpSession:
    def __init__(self, url: str, token: str, timeout_seconds: float):
        self.url = url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.client: httpx.AsyncClient | None = None
        self.headers: dict[str, str] = {}
        self.request_id = 1

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            base_headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
            response = await self.client.post(
                self.url,
                headers=base_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": self.request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "front-agent", "version": "1.0"},
                    },
                },
            )
            response.raise_for_status()
            payload = _decode_response(response) or {}
            if payload.get("error"):
                raise BillingGatewayError(str(payload["error"]))

            self.headers = dict(base_headers)
            session_id = response.headers.get("mcp-session-id")
            if session_id:
                self.headers["Mcp-Session-Id"] = session_id
            initialized = await self.client.post(
                self.url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
            )
            initialized.raise_for_status()
            return self
        except Exception:
            await self.client.aclose()
            raise

    async def __aexit__(self, exc_type, exc, traceback):
        if self.client is not None:
            await self.client.aclose()

    async def query(self, database: str, sql: str, ticket_id: str) -> list[dict[str, str]]:
        if self.client is None:
            raise BillingGatewayError("MCP session is not initialized")
        self.request_id += 1
        response = await self.client.post(
            self.url,
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "tools/call",
                "params": {
                    "name": "db_gateway_query",
                    "arguments": {
                        "database": database,
                        "sql": sql,
                        "ticket_id": ticket_id,
                    },
                },
            },
        )
        response.raise_for_status()
        payload = _decode_response(response)
        if payload is None:
            raise BillingGatewayError("DB Gateway returned an empty response")
        return _gateway_rows(payload)


def _tenant_ids(rows: list[dict[str, str]]) -> list[str]:
    tenant_ids = []
    for row in rows:
        try:
            tenant_id = str(uuid.UUID(row.get("tenant_id") or ""))
        except (ValueError, AttributeError):
            continue
        if tenant_id not in tenant_ids:
            tenant_ids.append(tenant_id)
    return tenant_ids


def _compact(row: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in row.items() if value not in (None, "")}


async def lookup_billing(email: str, ticket_id: str) -> dict[str, Any]:
    """Return a sender-bound, read-only Dify Cloud billing snapshot."""
    from config import settings

    try:
        normalized_email = _normalize_email(email)
    except ValueError:
        return {
            "status": "unavailable",
            "message": "Billing lookup requires a valid trusted Front sender email.",
        }
    if not settings.dify_db_mcp_token:
        return {
            "status": "not_configured",
            "message": "Billing lookup is unavailable because its runtime token is not configured.",
        }

    email_literal = _sql_literal(normalized_email)
    account_sql = f"""
        SELECT
            a.id AS account_id,
            a.email,
            a.status AS account_status,
            a.created_at AS account_created_at,
            a.last_login_at,
            a.last_active_at,
            j.tenant_id,
            j.role AS tenant_role,
            j.current AS current_tenant,
            t.name AS workspace_name,
            t.status AS workspace_status,
            t.plan AS workspace_plan
        FROM accounts a
        LEFT JOIN tenant_account_joins j ON j.account_id = a.id
        LEFT JOIN tenants t ON t.id = j.tenant_id
        WHERE lower(a.email) = lower({email_literal})
        ORDER BY j.current DESC NULLS LAST, j.updated_at DESC NULLS LAST
        LIMIT 20
    """
    deletion_sql = f"""
        SELECT account_id, reason, created_at
        FROM account_deletion_logs
        WHERE lower(email) = lower({email_literal})
        ORDER BY created_at DESC
        LIMIT 10
    """
    audit_id = (ticket_id or "front-agent-billing")[:200]

    try:
        async with _McpSession(
            settings.dify_db_mcp_url,
            settings.dify_db_mcp_token,
            settings.dify_db_mcp_timeout_seconds,
        ) as session:
            account_rows = await session.query("prod", account_sql, audit_id)
            deletion_rows = await session.query("billing", deletion_sql, audit_id)
            tenant_ids = _tenant_ids(account_rows)
            subscription_rows: list[dict[str, str]] = []
            usage_rows: list[dict[str, str]] = []

            if tenant_ids:
                tenant_filter = ", ".join(_sql_literal(value) for value in tenant_ids)
                subscription_sql = f"""
                    SELECT
                        s.tenant_id,
                        s.plan,
                        s.interval,
                        s.expiration_date,
                        st.subscription_status,
                        st.cancel_at_period_end,
                        st.current_period_start,
                        st.current_period_end,
                        st.last_payment_succeeded_at,
                        st.last_payment_failed_at
                    FROM tenant_subscription_settings s
                    LEFT JOIN tenant_stripe_status st ON st.tenant_id = s.tenant_id
                    WHERE s.tenant_id IN ({tenant_filter})
                    ORDER BY s.created_at DESC, st.updated_at DESC NULLS LAST
                    LIMIT 50
                """
                usage_sql = f"""
                    SELECT DISTINCT ON (tenant_id, feature_key, bucket)
                        tenant_id, feature_key, quota, usage, plan, bucket, updated_at
                    FROM tenant_feature_usages
                    WHERE tenant_id IN ({tenant_filter})
                    ORDER BY tenant_id, feature_key, bucket, updated_at DESC
                    LIMIT 100
                """
                subscription_rows = await session.query(
                    "billing", subscription_sql, audit_id
                )
                usage_rows = await session.query("billing", usage_sql, audit_id)
    except (httpx.HTTPError, BillingGatewayError):
        return {
            "status": "unavailable",
            "message": (
                "Billing lookup failed; continue the support flow without treating "
                "this as evidence about the customer's account."
            ),
        }

    account = {}
    workspaces = []
    if account_rows:
        first = account_rows[0]
        account = _compact({
            key: first.get(key, "")
            for key in (
                "account_status",
                "account_created_at",
                "last_login_at",
                "last_active_at",
            )
        })
        for row in account_rows:
            if row.get("tenant_id"):
                workspaces.append(_compact({
                    key: row.get(key, "")
                    for key in (
                        "workspace_name",
                        "workspace_status",
                        "workspace_plan",
                        "tenant_role",
                        "current_tenant",
                    )
                }))

    return {
        "status": "ok",
        "found": bool(account_rows),
        "account": account,
        "workspaces": workspaces,
        "deletion_history": [_compact(row) for row in deletion_rows],
        "subscriptions": [_compact(row) for row in subscription_rows],
        "feature_usage": [_compact(row) for row in usage_rows],
        "limitations": (
            "This snapshot does not contain complete invoice or card-charge records "
            "and cannot authorize refunds, cancellations, or quota changes. A missing "
            "account is not proof that the customer is self-hosted."
        ),
    }
