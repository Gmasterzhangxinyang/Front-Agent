# Runtime Boundary Hardening Design

## Goal

Harden the current stable-agent-v2 runtime at the three boundaries with the
highest immediate risk:

1. Treat every LLM tool call as untrusted input and bind it to the active
   conversation.
2. Require an explicit webhook trust configuration and constrain attachment
   downloads.
3. Return a retryable HTTP status after handler failures and allow failed
   conversations to be processed again.

The change must preserve the existing deterministic routing and skill behavior.

## Scope

### Included

- Central validation and context binding for tool calls produced by the LLM.
- Secure-by-default Front webhook signature configuration.
- Attachment URL, count, byte-size, and extracted-text limits.
- HTTP 503 responses after handler failures.
- Re-entry for conversations in `failed_needs_review`.
- Offline regression tests for each boundary.
- Configuration and operator documentation updates.

### Not Included

- Ops dashboard authentication.
- Durable webhook queues or background workers.
- Outbox/reservation-based side-effect idempotency.
- Conversation ordering, pagination, or role normalization.
- Scheduler behavior.
- General tool registry refactoring unrelated to the boundary checks.

## 1. LLM Tool Call Boundary

### Execution Context

Introduce an immutable execution context for LLM-originated tool calls:

```python
@dataclass(frozen=True)
class ToolExecutionContext:
    conversation_id: str
    sender_email: str = ""
```

The orchestrator creates this context from trusted webhook/state data. The
model never creates or modifies it.

### Validation

Build a tool schema lookup from `TOOL_SCHEMAS`. Before an LLM-originated call
reaches `execute_tool_call`, a single preparation function must:

1. Reject tool names not present in `TOOL_SCHEMAS`.
2. Require the arguments to be a JSON object.
3. Reject missing required properties.
4. Reject properties not declared by the selected tool schema.
5. Validate declared primitive types and enum values used by the current
   schemas.
6. Override every declared `conversation_id` with the context value.
7. Add the trusted `to_email` only after validation for
   `front_create_draft`.

This ordering is important: a model-supplied `to_email` is an unknown field and
is rejected, while the internal trusted field remains available to the draft
implementation.

Validation failures are returned to the model as a deterministic
`tool_validation_failed` tool result. They do not execute a side effect and do
not abort the entire webhook request. Internal Python routing continues to use
`execute_tool_call` directly and is not constrained by the LLM schema lookup.

## 2. Webhook Trust Configuration

Add `allow_unsigned_front_webhooks: bool = False` to settings.

At application startup:

- A configured `FRONT_WEBHOOK_SECRET` is accepted.
- If the secret is empty and `ALLOW_UNSIGNED_FRONT_WEBHOOKS` is false, startup
  fails with a clear configuration error.
- If unsigned webhooks are explicitly enabled, startup succeeds and emits a
  prominent warning for local development.

The request-level verifier also fails closed when the secret is empty unless
the explicit override is enabled. This keeps direct unit use and future entry
points secure even if startup validation is bypassed.

## 3. Attachment Download Boundary

### Configuration

Add the following settings with conservative defaults:

```text
FRONT_ATTACHMENT_ALLOWED_HOSTS=api2.frontapp.com
MAX_ATTACHMENT_COUNT=5
MAX_ATTACHMENT_BYTES=10485760
MAX_ATTACHMENT_TEXT_CHARS=50000
```

The host setting is a comma-separated exact allowlist so production can add a
Front-managed attachment host without a code change.

### URL Validation

Before a request is made, attachment URLs must:

- use HTTPS;
- contain no embedded username or password;
- use no non-default port;
- have a hostname exactly present in the configured allowlist.

The Front bearer token is attached only after this validation succeeds.

### Streaming and Limits

`get_attachment` uses a streaming response. It rejects an oversized declared
`Content-Length` and also enforces the byte limit while reading chunks, because
the header may be absent or incorrect.

The orchestrator considers only the first `MAX_ATTACHMENT_COUNT` attachments.
Extracted document text is truncated to `MAX_ATTACHMENT_TEXT_CHARS` before it
enters a model prompt. Existing behavior remains fail-soft: an invalid or
oversized attachment is logged and skipped while the email body is still
processed.

## 4. Handler Failure and Retry Semantics

After an unexpected handler exception, the webhook path retains its current
best-effort cleanup:

1. notify Bobby through the deduplicated tool path;
2. reopen the Front conversation;
3. save `failed_needs_review` with a bounded error summary.

It then raises HTTP 503 instead of returning a JSON body with HTTP 200. The
event is not added to `webhook_events`.

On the next delivery, `handle_email` treats `failed_needs_review` as a retryable
entry state and runs the initial classification/route flow again. Existing
action-log deduplication protects already-recorded successful side effects.
Other completed non-education states keep their current skip behavior.

This design intentionally does not distinguish permanent and transient handler
exceptions. Durable retry policies belong to the future queue/outbox work.

## 5. Tests

Add standalone offline tests compatible with the repository's current test
runner style. They must cover:

- a model-supplied different `conversation_id` is replaced;
- a model-supplied `to_email` is rejected;
- unknown and missing tool arguments are rejected without side effects;
- an unconfigured webhook secret fails closed;
- the explicit unsigned-development override is honored;
- non-HTTPS and non-allowlisted attachment URLs are rejected before I/O;
- declared and streamed attachment sizes are capped;
- attachment count and extracted text are capped;
- handler exceptions result in HTTP 503 and no processed event record;
- `failed_needs_review` enters the new-message flow on retry.

Run the existing routing, skill, and draft-adoption tests in addition to the new
suite. No test may make a real Front, OpenAI, Linear, or Feishu request.

## Success Criteria

- LLM output cannot select a different conversation or customer recipient.
- An unsigned webhook cannot be accepted without an explicit development flag.
- Front credentials are never sent to an unapproved attachment host.
- Attachment memory and prompt growth have deterministic upper bounds.
- Unexpected handler failures return HTTP 503 and remain retryable.
- Existing deterministic routes and skill policy tests still pass.
