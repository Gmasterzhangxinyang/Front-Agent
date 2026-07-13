# Runtime Boundary Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent LLM-originated cross-conversation actions, fail closed for unsigned webhooks and unsafe attachments, and report handler failures truthfully without recording them as processed.

**Architecture:** Add one centralized preparation boundary for LLM tool calls while keeping internal deterministic tool calls unchanged. Add secure runtime configuration checks at application startup, validate and stream attachment downloads with hard limits, and change failed webhook processing to return HTTP 503 while allowing `failed_needs_review` states to re-enter the initial flow.

**Tech Stack:** Python 3.11, FastAPI, Pydantic Settings, SQLAlchemy async, HTTPX, unittest.mock, standalone repository test scripts.

## Global Constraints

- Preserve deterministic routing and existing skill behavior.
- Do not modify or stage the user's existing changes in `routes/ops.py`, `skills/education.md`, `tasks/scheduler.py`, `tests/test_routing.py`, or `tests/test_skills.py`.
- Do not add a durable queue, outbox, scheduler changes, Ops authentication, conversation reordering, or pagination.
- Tests must not call Front, OpenAI, Linear, Feishu, or any other network service.
- Unsigned Front webhooks are disabled by default and require `ALLOW_UNSIGNED_FRONT_WEBHOOKS=true` for explicit local use.
- Default attachment limits are 5 files, 10 MiB per file, and 50,000 extracted text characters.
- Only exact HTTPS hosts in `FRONT_ATTACHMENT_ALLOWED_HOSTS` may receive the Front bearer token.

---

## File Map

- Create `tests/test_runtime_boundaries.py`: standalone offline regression suite for all new boundaries.
- Modify `agent/tool_registry.py`: immutable tool execution context and schema-driven LLM argument preparation.
- Modify `agent/orchestrator.py`: use prepared LLM arguments, trusted context, attachment count limit, and failed-state retry entry.
- Modify `config.py`: webhook and attachment security settings.
- Modify `webhooks/front_webhook.py`: fail-closed signature configuration and HTTP 503 failure behavior.
- Modify `main.py`: startup security validation.
- Modify `tools/front.py`: attachment URL validation and bounded streaming download.
- Modify `tools/attachments.py`: attachment list/text bounds and observable fail-soft behavior.
- Modify `.env.example` and `README.md`: document secure runtime configuration.
- Modify `record.md`: record the completed security and reliability fix.

---

### Task 1: Centralize LLM Tool Validation and Context Binding

**Files:**
- Create: `tests/test_runtime_boundaries.py`
- Modify: `agent/tool_registry.py`
- Modify: `agent/orchestrator.py`

**Interfaces:**
- Produces: `ToolExecutionContext(conversation_id: str, sender_email: str = "")`
- Produces: `ToolCallValidationError(ValueError)`
- Produces: `prepare_llm_tool_call(tool_name: str, args: dict, context: ToolExecutionContext) -> dict`
- Consumes: existing `TOOL_SCHEMAS` and `execute_tool_call`

- [x] **Step 1: Write failing tool-boundary tests**

Create `tests/test_runtime_boundaries.py` with:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tool_registry import (
    ToolCallValidationError,
    ToolExecutionContext,
    prepare_llm_tool_call,
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
            "reason_cn": "文档指引",
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
                "reason_cn": "文档指引",
                "to_email": "attacker@example.net",
            },
            _context(),
        )
    except ToolCallValidationError as exc:
        assert "unknown arguments: to_email" in str(exc)
    else:
        raise AssertionError("model-supplied to_email must be rejected")


def test_llm_tool_rejects_missing_unknown_and_invalid_arguments():
    invalid_calls = [
        (
            "front_create_draft",
            {"conversation_id": "cnv_trusted", "body": "Missing fields"},
            "missing required arguments",
        ),
        (
            "front_add_comment",
            {
                "conversation_id": "cnv_trusted",
                "body": "Comment",
                "extra": "not allowed",
            },
            "unknown arguments: extra",
        ),
        (
            "front_forward_to_community",
            {
                "conversation_id": "cnv_trusted",
                "summary": "Summary",
                "region": "moon",
            },
            "invalid enum value for region",
        ),
    ]
    for tool_name, args, expected in invalid_calls:
        try:
            prepare_llm_tool_call(tool_name, args, _context())
        except ToolCallValidationError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"{tool_name} validation should fail")


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("runtime boundary tests passed")
```

- [x] **Step 2: Run the new suite and verify the import failure**

Run: `.venv/bin/python tests/test_runtime_boundaries.py`

Expected: FAIL because `ToolCallValidationError`, `ToolExecutionContext`, and `prepare_llm_tool_call` do not exist.

- [x] **Step 3: Add the tool execution context and schema validator**

In `agent/tool_registry.py`, import `dataclass`, then add these definitions immediately after `TOOL_SCHEMAS`:

```python
@dataclass(frozen=True)
class ToolExecutionContext:
    conversation_id: str
    sender_email: str = ""


class ToolCallValidationError(ValueError):
    pass


TOOL_SCHEMAS_BY_NAME = {
    item["function"]["name"]: item["function"]
    for item in TOOL_SCHEMAS
}


def _matches_json_type(value, expected_type: str) -> bool:
    validators = {
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
    }
    validator = validators.get(expected_type)
    return True if validator is None else validator(value)


def prepare_llm_tool_call(
    tool_name: str,
    args: dict,
    context: ToolExecutionContext,
) -> dict:
    schema = TOOL_SCHEMAS_BY_NAME.get(tool_name)
    if schema is None:
        raise ToolCallValidationError(f"unknown tool: {tool_name}")
    if not isinstance(args, dict):
        raise ToolCallValidationError("arguments must be a JSON object")

    parameters = schema["parameters"]
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    missing = sorted(required - set(args))
    if missing:
        raise ToolCallValidationError(
            "missing required arguments: " + ", ".join(missing)
        )

    unknown = sorted(set(args) - set(properties))
    if unknown:
        raise ToolCallValidationError(
            "unknown arguments: " + ", ".join(unknown)
        )

    for name, value in args.items():
        property_schema = properties[name]
        expected_type = property_schema.get("type")
        if expected_type and not _matches_json_type(value, expected_type):
            raise ToolCallValidationError(
                f"invalid type for {name}: expected {expected_type}"
            )
        allowed_values = property_schema.get("enum")
        if allowed_values is not None and value not in allowed_values:
            raise ToolCallValidationError(
                f"invalid enum value for {name}: {value}"
            )

    prepared = dict(args)
    if "conversation_id" in properties:
        prepared["conversation_id"] = context.conversation_id
    if tool_name == "front_create_draft" and context.sender_email:
        prepared["to_email"] = context.sender_email
    return prepared
```

- [x] **Step 4: Bind every LLM call in the orchestrator**

In `agent/orchestrator.py`:

1. Import `ToolCallValidationError`, `ToolExecutionContext`, and `prepare_llm_tool_call`.
2. Add required `conversation_id: str` to `_run_agent_loop`.
3. Pass `conversation_id=conversation_id` at both call sites.
4. Immediately before `for _ in range(max_iterations):`, create the trusted
   context:

```python
    context = ToolExecutionContext(
        conversation_id=conversation_id,
        sender_email=sender_email,
    )
```

5. Inside `for tc in msg.tool_calls:`, replace the current permissive
   `json.loads` exception block with:

```python
            tool_name = tc.function.name
            try:
                raw_args = json.loads(tc.function.arguments)
                args = prepare_llm_tool_call(tool_name, raw_args, context)
            except (json.JSONDecodeError, ToolCallValidationError) as exc:
                result = f"tool_validation_failed: {exc}"
                logger.warning("Rejected LLM tool call %s: %s", tool_name, exc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                continue
```

Keep Bobby handoff deduplication after this validation block so its key uses the
trusted conversation ID. Remove:

```python
            if tool_name == "front_create_draft" and sender_email and not args.get("to_email"):
                args["to_email"] = sender_email
```

- [x] **Step 5: Run focused and existing tests**

Run:

```bash
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
```

Expected: all three scripts exit 0 and print their passing messages.

- [x] **Step 6: Commit only Task 1 files**

```bash
git add agent/tool_registry.py agent/orchestrator.py tests/test_runtime_boundaries.py
git diff --cached --check
git commit -m "fix: bind llm tool calls to trusted context"
```

---

### Task 2: Fail Closed for Unsigned Webhooks

**Files:**
- Modify: `config.py`
- Modify: `webhooks/front_webhook.py`
- Modify: `main.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/test_runtime_boundaries.py`

**Interfaces:**
- Produces: `validate_webhook_security_config() -> None`
- Consumes: `settings.front_webhook_secret`
- Consumes: `settings.allow_unsigned_front_webhooks`

- [x] **Step 1: Add failing signature configuration tests**

Append these imports and tests to `tests/test_runtime_boundaries.py`:

```python
from unittest.mock import patch

from config import settings
from webhooks.front_webhook import (
    validate_webhook_security_config,
    verify_signature,
)


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
    ):
        validate_webhook_security_config()
        assert verify_signature(b"{}", "")
```

- [x] **Step 2: Run the suite and verify the missing-interface failure**

Run: `.venv/bin/python tests/test_runtime_boundaries.py`

Expected: FAIL because `validate_webhook_security_config` and `allow_unsigned_front_webhooks` do not exist.

- [x] **Step 3: Add secure webhook configuration**

Add to `Settings` in `config.py`:

```python
    # Webhook security. Unsigned requests require an explicit local-only opt-out.
    allow_unsigned_front_webhooks: bool = False
```

In `webhooks/front_webhook.py`, add:

```python
def validate_webhook_security_config() -> None:
    if settings.front_webhook_secret:
        return
    if settings.allow_unsigned_front_webhooks:
        logger.warning(
            "Front webhook signature verification is explicitly disabled"
        )
        return
    raise RuntimeError(
        "FRONT_WEBHOOK_SECRET is required unless "
        "ALLOW_UNSIGNED_FRONT_WEBHOOKS=true"
    )
```

Replace the empty-secret branch in `verify_signature` with:

```python
    if not settings.front_webhook_secret:
        return settings.allow_unsigned_front_webhooks
```

In `main.py`, import and call the validator before database initialization:

```python
from webhooks.front_webhook import (
    router as webhook_router,
    validate_webhook_security_config,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_webhook_security_config()
    await init_db()
    if settings.enable_scheduler:
        start_scheduler()
    yield
```

- [x] **Step 4: Document the explicit local override**

Add to `.env.example` below `FRONT_WEBHOOK_SECRET`:

```text
# Local development only. Keep false in production.
ALLOW_UNSIGNED_FRONT_WEBHOOKS=false
```

Add to the README configuration and local-run sections:

```markdown
`FRONT_WEBHOOK_SECRET` is required by default. For local webhook fixtures only,
set `ALLOW_UNSIGNED_FRONT_WEBHOOKS=true`; never enable it in production.
```

- [x] **Step 5: Run focused and startup compilation checks**

Run:

```bash
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python -m py_compile config.py main.py webhooks/front_webhook.py
```

Expected: both commands exit 0.

- [x] **Step 6: Commit only Task 2 files**

```bash
git add config.py webhooks/front_webhook.py main.py .env.example README.md tests/test_runtime_boundaries.py
git diff --cached --check
git commit -m "fix: require explicit webhook trust configuration"
```

---

### Task 3: Constrain Attachment Downloads and Prompt Growth

**Files:**
- Modify: `config.py`
- Modify: `tools/front.py`
- Modify: `tools/attachments.py`
- Modify: `agent/orchestrator.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/test_runtime_boundaries.py`

**Interfaces:**
- Produces: `AttachmentDownloadRejected(ValueError)`
- Produces: `AttachmentTooLarge(ValueError)`
- Produces: `validate_attachment_url(attachment_url: str) -> str`
- Produces: `read_limited_attachment(response: httpx.Response, max_bytes: int) -> bytes`
- Produces: `bounded_attachments(attachments: list[dict]) -> list[dict]`
- Produces: `clip_attachment_text(text: str) -> str`

- [x] **Step 1: Add failing attachment boundary tests**

Append these imports, helper, and tests to `tests/test_runtime_boundaries.py`:

```python
import asyncio

import httpx

from tools.attachments import bounded_attachments, clip_attachment_text
from tools.front import (
    AttachmentDownloadRejected,
    AttachmentTooLarge,
    read_limited_attachment,
    validate_attachment_url,
)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        return None


def test_attachment_url_requires_https_and_exact_allowed_host():
    with patch.object(
        settings,
        "front_attachment_allowed_hosts",
        "api2.frontapp.com,files.frontapp.com",
    ):
        assert (
            validate_attachment_url(
                "https://api2.frontapp.com/download/attachment"
            )
            == "https://api2.frontapp.com/download/attachment"
        )
        rejected = [
            "http://api2.frontapp.com/download/attachment",
            "https://api2.frontapp.com.evil.test/attachment",
            "https://user:pass@api2.frontapp.com/attachment",
            "https://api2.frontapp.com:8443/attachment",
        ]
        for url in rejected:
            try:
                validate_attachment_url(url)
            except AttachmentDownloadRejected:
                pass
            else:
                raise AssertionError(f"unsafe attachment URL accepted: {url}")


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
    ):
        assert len(bounded_attachments(attachments)) == 5
        assert clip_attachment_text("1234567890") == "12345678"
```

- [x] **Step 2: Run the suite and verify the missing-interface failure**

Run: `.venv/bin/python tests/test_runtime_boundaries.py`

Expected: FAIL because the attachment boundary classes and functions do not exist.

- [x] **Step 3: Add attachment limit settings**

Add to `Settings` in `config.py`:

```python
    # Attachment downloads are authenticated with the Front token.
    front_attachment_allowed_hosts: str = "api2.frontapp.com"
    max_attachment_count: int = 5
    max_attachment_bytes: int = 10 * 1024 * 1024
    max_attachment_text_chars: int = 50_000
```

- [x] **Step 4: Implement exact-host validation and bounded streaming**

In `tools/front.py`, import `urlsplit` from `urllib.parse` and add:

```python
class AttachmentDownloadRejected(ValueError):
    pass


class AttachmentTooLarge(ValueError):
    pass


def _attachment_allowed_hosts() -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in settings.front_attachment_allowed_hosts.split(",")
        if host.strip()
    }


def validate_attachment_url(attachment_url: str) -> str:
    try:
        parsed = urlsplit(attachment_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise AttachmentDownloadRejected("invalid attachment URL") from exc

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https":
        raise AttachmentDownloadRejected("attachment URL must use HTTPS")
    if parsed.username or parsed.password:
        raise AttachmentDownloadRejected("attachment URL cannot contain credentials")
    if port not in (None, 443):
        raise AttachmentDownloadRejected("attachment URL uses a non-default port")
    if hostname not in _attachment_allowed_hosts():
        raise AttachmentDownloadRejected(
            f"attachment host is not allowed: {hostname or '<missing>'}"
        )
    return attachment_url


async def read_limited_attachment(
    response: httpx.Response,
    max_bytes: int,
) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > max_bytes:
            raise AttachmentTooLarge(
                f"attachment exceeds {max_bytes} bytes"
            )

    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > max_bytes:
            raise AttachmentTooLarge(
                f"attachment exceeds {max_bytes} bytes"
            )
        content.extend(chunk)
    return bytes(content)
```

Replace `get_attachment` with:

```python
async def get_attachment(attachment_url: str) -> bytes:
    validated_url = validate_attachment_url(attachment_url)
    headers = {"Authorization": f"Bearer {settings.front_api_token}"}
    async with httpx.AsyncClient(timeout=FRONT_TIMEOUT) as client:
        async with client.stream(
            "GET",
            validated_url,
            headers=headers,
        ) as response:
            response.raise_for_status()
            return await read_limited_attachment(
                response,
                settings.max_attachment_bytes,
            )
```

- [x] **Step 5: Bound attachment selection and extracted text**

In `tools/attachments.py`, add `logging` and `settings`, define a module logger, and add:

```python
logger = logging.getLogger(__name__)


def bounded_attachments(attachments: list[dict]) -> list[dict]:
    limit = max(0, settings.max_attachment_count)
    if len(attachments) > limit:
        logger.warning(
            "Ignoring %s attachments above configured limit %s",
            len(attachments) - limit,
            limit,
        )
    return attachments[:limit]


def clip_attachment_text(text: str) -> str:
    limit = max(0, settings.max_attachment_text_chars)
    return text[:limit]
```

Use `clip_attachment_text(text)` before appending extracted document text. Replace silent outer exception handlers with:

```python
        except Exception as exc:
            logger.warning(
                "Failed to load attachment %s: %s",
                att.get("filename", "attachment"),
                exc,
            )
```

In `agent/orchestrator.py`, import `bounded_attachments` and apply it before both attachment processing calls:

```python
    bounded = bounded_attachments(attachments)
    attachment_content = await fetch_attachments_as_base64(bounded)
    doc_attachments = await fetch_attachments_as_text(bounded)
```

- [x] **Step 6: Document attachment settings**

Add to `.env.example`:

```text
FRONT_ATTACHMENT_ALLOWED_HOSTS=api2.frontapp.com
MAX_ATTACHMENT_COUNT=5
MAX_ATTACHMENT_BYTES=10485760
MAX_ATTACHMENT_TEXT_CHARS=50000
```

Add the same variables to the README configuration example and explain that the host list must contain only exact Front-managed HTTPS hosts used by the deployment.

- [x] **Step 7: Run focused and regression tests**

Run:

```bash
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
```

Expected: all four scripts exit 0.

- [x] **Step 8: Commit only Task 3 files**

```bash
git add config.py tools/front.py tools/attachments.py agent/orchestrator.py .env.example README.md tests/test_runtime_boundaries.py
git diff --cached --check
git commit -m "fix: constrain authenticated attachment downloads"
```

---

### Task 4: Return HTTP 503 and Re-enter Failed Conversations

**Files:**
- Modify: `agent/orchestrator.py`
- Modify: `webhooks/front_webhook.py`
- Modify: `tests/test_runtime_boundaries.py`

**Interfaces:**
- Produces: `is_failed_retry_state(existing_state) -> bool`
- Consumes: `execute_tool_call` for deduplicated Bobby failure notification.
- Preserves: event rows are created only after successful handling.

- [x] **Step 1: Add failing failed-state and HTTP status tests**

Append these imports, fakes, and tests to `tests/test_runtime_boundaries.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from agent.orchestrator import is_failed_retry_state
from webhooks import front_webhook as webhook_module


class _ScalarResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __init__(self):
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return _ScalarResult()

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        return None


class _InboxResponse:
    status_code = 200

    def json(self):
        return {"_results": [{"id": "inb_f9fvf"}]}


def test_failed_needs_review_is_retryable():
    assert is_failed_retry_state(
        SimpleNamespace(step="failed_needs_review")
    )
    assert not is_failed_retry_state(SimpleNamespace(step="draft_created"))
    assert not is_failed_retry_state(None)


def test_handler_failure_is_not_acknowledged_or_recorded():
    session = _FakeSession()
    payload = {
        "target": {
            "data": {
                "type": "email",
                "is_inbound": True,
                "text": "Help",
                "from": {"handle": "customer@example.com"},
            }
        }
    }

    async def run_case():
        with (
            patch.object(
                webhook_module,
                "AsyncSessionLocal",
                lambda: session,
            ),
            patch.object(
                webhook_module,
                "handle_email",
                AsyncMock(side_effect=RuntimeError("temporary failure")),
            ),
            patch(
                "tools.front.front_request",
                AsyncMock(return_value=_InboxResponse()),
            ),
            patch(
                "tools.front.reopen_conversation",
                AsyncMock(return_value=True),
            ),
            patch(
                "tools.state.set_state",
                AsyncMock(return_value=None),
            ),
            patch(
                "agent.tool_registry.execute_tool_call",
                AsyncMock(return_value="forwarded"),
            ),
        ):
            try:
                await webhook_module._process_front_webhook_event(
                    payload,
                    "evt_retry",
                    "cnv_retry",
                )
            except HTTPException as exc:
                assert exc.status_code == 503
                assert exc.detail == "handler_error"
            else:
                raise AssertionError("handler failure must not return success")

    asyncio.run(run_case())
    assert session.added == []
```

- [x] **Step 2: Run the suite and verify both behaviors fail**

Run: `.venv/bin/python tests/test_runtime_boundaries.py`

Expected: FAIL because `is_failed_retry_state` does not exist and the handler currently returns HTTP 200.

- [x] **Step 3: Let failed states re-enter the initial flow**

In `agent/orchestrator.py`, add:

```python
def is_failed_retry_state(existing_state) -> bool:
    return bool(
        existing_state
        and existing_state.step == "failed_needs_review"
    )
```

At the start of `handle_email`, preserve existing behavior except for failed states:

```python
    existing_state = await state_tool.get_state(db, conversation_id)
    retrying_failed_state = is_failed_retry_state(existing_state)

    if existing_state and not retrying_failed_state:
        category = existing_state.category or ""
        step = existing_state.step or ""
        if category != "education":
            logger.info(
                "Skipping non-education reply for conv %s - "
                "step=%s category=%s",
                conversation_id,
                existing_state.step,
                existing_state.category,
            )
            return
        if step == "closed_spam":
            logger.info(
                "Skipping closed spam conversation %s",
                conversation_id,
            )
            return
```

Include `failed_needs_review` in both initial-flow checks:

```python
    if (
        not existing_state
        or existing_state.step in ("initial", "done", "failed_needs_review")
    ):
```

This same condition must be used for prompt selection and classification/route selection.

- [x] **Step 4: Deduplicate the failure handoff and return HTTP 503**

In the handler exception block in `webhooks/front_webhook.py`, replace the direct handoff call with:

```python
            try:
                from agent.tool_registry import execute_tool_call

                notify_result = await execute_tool_call(
                    "front_forward_to_bobby",
                    {
                        "message": error_summary,
                        "conversation_id": conversation_id,
                    },
                    db,
                )
                if "failed" in notify_result:
                    logger.warning(
                        "Failed to forward handler error for %s: %s",
                        conversation_id,
                        notify_result,
                    )
            except Exception as notify_error:
                logger.warning(
                    "Failed to forward handler error for %s: %s",
                    conversation_id,
                    notify_error,
                )
```

Replace the final successful return from the exception path with:

```python
            raise HTTPException(
                status_code=503,
                detail="handler_error",
            ) from e
```

Do not add the event to `webhook_events` in this branch.

- [x] **Step 5: Run focused and full repository verification**

Run:

```bash
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m py_compile config.py main.py agent/orchestrator.py agent/tool_registry.py tools/front.py tools/attachments.py webhooks/front_webhook.py tests/test_runtime_boundaries.py
.venv/bin/python -m pip check
git diff --check
```

Expected: every command exits 0.

- [x] **Step 6: Record and commit the completed runtime hardening**

Append to `record.md`:

```markdown
- [fix] bind LLM tools to trusted conversation context, require explicit webhook trust, bound authenticated attachments, and return truthful handler failures without recording them as processed (agent/orchestrator.py, agent/tool_registry.py, config.py, main.py, tools/attachments.py, tools/front.py, webhooks/front_webhook.py, tests/test_runtime_boundaries.py)
```

Then commit only Task 4 and the record:

```bash
git add agent/orchestrator.py webhooks/front_webhook.py tests/test_runtime_boundaries.py record.md
git diff --cached --check
git commit -m "fix: preserve retry semantics after handler failures"
```

- [x] **Step 7: Confirm the final worktree and commits**

Run:

```bash
git status --short --branch
git log -5 --oneline
```

Expected: the five user-owned modified files remain unstaged, no implementation file is left uncommitted, and the runtime hardening commits appear above design commit `3d00107`.
