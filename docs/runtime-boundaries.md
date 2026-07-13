# Runtime Security and Retry Boundaries

This document describes the runtime boundaries that protect Front webhook
processing, authenticated attachment downloads, and LLM-triggered tool calls.

## Boundary Summary

| Boundary | Runtime behavior |
|---|---|
| Webhook trust | Startup requires `FRONT_WEBHOOK_SECRET` unless unsigned webhooks are explicitly enabled for local fixtures. |
| LLM tools | Model arguments are checked against the registered schema before execution. |
| Trusted context | Conversation IDs and draft recipients come from the webhook/state context, not model output. |
| Attachments | Only exact allowlisted HTTPS hosts receive the Front bearer token. Downloads, counts, and extracted text are bounded. |
| Handler failures | Unexpected processing failures return HTTP 503, remain unrecorded in `webhook_events`, and can be retried. |
| Retry deduplication | Failure handoffs use the action log so repeated deliveries do not repeat successful notifications. |

## Required Configuration

Production must set a real webhook secret:

```bash
FRONT_WEBHOOK_SECRET=replace-with-real-secret
ALLOW_UNSIGNED_FRONT_WEBHOOKS=false
```

`ALLOW_UNSIGNED_FRONT_WEBHOOKS=true` is only for local fixtures that cannot
sign requests. Do not use it in production.

Attachment defaults:

```bash
FRONT_ATTACHMENT_ALLOWED_HOSTS=api2.frontapp.com
MAX_ATTACHMENT_COUNT=5
MAX_ATTACHMENT_BYTES=10485760
MAX_ATTACHMENT_TEXT_CHARS=50000
```

`FRONT_ATTACHMENT_ALLOWED_HOSTS` is a comma-separated list of exact hostnames.
Do not add wildcard domains. Add a host only after confirming that Front uses it
for authenticated attachment downloads in the target environment.

## Attachment Behavior

An attachment URL is rejected before creating an HTTP client when it:

- is not HTTPS;
- contains embedded credentials;
- uses a non-default port;
- does not exactly match an allowed hostname.

The downloader rejects oversized `Content-Length` values and also enforces the
limit while streaming, so a missing or false header cannot bypass the cap.
Rejected or unreadable attachments are logged and skipped; the email body can
still be processed. Only the configured number of attachments is considered,
and extracted document text is clipped before entering the LLM prompt.

## Tool Execution Behavior

LLM-originated tool calls reject unknown tools, missing or extra arguments,
invalid types, and invalid enum values. The orchestrator then replaces any
model-provided conversation ID with the trusted current conversation ID.
`front_create_draft` also receives the original sender address from trusted
state immediately before the Front side effect.

Deterministic Python routes continue to call the internal dispatcher directly.
They are not treated as untrusted model input.

## Failure and Retry Behavior

When `handle_email` raises unexpectedly, the webhook handler:

1. sends a deduplicated Bobby handoff through the tool registry;
2. reopens the Front conversation;
3. stores `failed_needs_review` with a bounded error summary;
4. does not add the event to `webhook_events`;
5. raises HTTP 503 so Front can retry the delivery.

On retry, `failed_needs_review` re-enters the initial classification flow. Other
existing conversation states keep their previous multi-turn behavior.

## Deploy Checklist

1. Set `FRONT_WEBHOOK_SECRET` in the deployment environment.
2. Keep `ALLOW_UNSIGNED_FRONT_WEBHOOKS=false` in production.
3. Confirm every required attachment hostname is explicitly allowlisted.
4. Review count, byte, and text limits for the deployment's expected traffic.
5. Run the verification commands below before restarting the service.
6. Send one signed test webhook and confirm `/health` and service logs after deployment.

## Verification

The repository tests are standalone Python scripts; `pytest` is not required.

```bash
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent tools webhooks tests config.py main.py
.venv/bin/python -m pip check
git diff --check
```

These tests are offline and do not call the live Front or LLM APIs. A signed
webhook smoke test is still required after deployment.
