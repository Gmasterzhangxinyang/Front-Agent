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
| Durable intake | Authenticated conversation webhooks are committed to `webhook_inbox` before immediate request-path processing. |
| Handler failures | Unexpected processing failures return HTTP 503, remain unrecorded in `webhook_events`, and stay recoverable in `webhook_inbox`. |
| Internal recovery | APScheduler checks due inbox rows every minute; Front Rule Webhooks themselves do not retry failed deliveries. |
| Retry deduplication | Failure handoffs use the action log so repeated deliveries do not repeat successful notifications. |

## Required Configuration

This service currently receives Front Rule Webhooks and validates their
HMAC-SHA1 `X-Front-Signature`. A Front company admin can copy the required value
from **Settings > Company > App store > Webhooks > Configure app > API secret**.
It is not `FRONT_API_TOKEN` and it is not an Application Webhook signing token.
See [Front Rule Webhooks](https://dev.frontapp.com/docs/rule-webhooks).

Production must set that value as the webhook secret:

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

## Durable Intake and Recovery Behavior

After signature validation and JSON/conversation validation, the service commits
the authenticated conversation event to `webhook_inbox`. It then immediately
claims and processes that row in the HTTP request path, so successful traffic
does not wait for a background poll.

When `handle_email` raises unexpectedly, the webhook handler:

1. sends a deduplicated Bobby handoff through the tool registry;
2. reopens the Front conversation;
3. stores `failed_needs_review` with a bounded error summary;
4. does not add the event to `webhook_events`;
5. schedules the durable inbox row for internal retry;
6. raises HTTP 503 instead of reporting a false success.

On a later attempt, `failed_needs_review` re-enters the initial classification
flow. Other existing conversation states keep their previous multi-turn
behavior.

Front's Rule Webhook documentation states that failed deliveries are not
automatically retried. The service therefore runs an internal APScheduler job
every minute. After the immediate attempt, failures use delays of 1, 5, 15, 60,
and 180 minutes. A failed attempt 6 transitions the row to `dead_letter` and
logs it for manual review.

Each processing claim has a 15-minute lease. If the process exits mid-attempt,
the scheduler can reclaim the expired row; an expired lease at the maximum
attempt count is terminalized as `dead_letter` without creating an extra
attempt. Successful rows become `processed` and have their payload cleared.
Dead-letter rows retain the original payload and a bounded error summary so an
operator can investigate and recover them.

`webhook_events` remains separate from the recovery inbox. It records only
events that finished successfully or were deterministically ignored. Retryable
failures are never inserted there, so recovery does not mistake a failed event
for completed work. Claims start only after the worker has both its conversation
lock and global execution capacity, so time spent queued does not age the lease.

## At-Least-Once Side Effects

Durable recovery guarantees at-least-once event processing, not exactly-once
external writes. `conversation_actions` prevents a repeat after its successful
record commits. An abrupt exit after Front, Linear, or another provider accepts
a write but before that local commit leaves an uncertain result; the recovered
event can repeat the write. Exactly-once behavior requires a stable provider
idempotency key or reconciliation of uncertain actions before retry.

Within one running service process, Linear creation has an additional 24-hour
cross-conversation guard keyed by the trusted sender and normalized original
message. Concurrent duplicate emails share a lock and reuse the first committed
ticket result even if the model generates different titles. This does not turn
the external Linear call into exactly-once behavior across process crashes or
multiple service replicas.

The FastAPI lifespan pauses APScheduler and waits up to 60 seconds for this
process's active jobs during a normal shutdown. This reduces the uncertain
window during planned deployments, but it does not protect against a timeout,
forced termination, host loss, or a provider response whose local commit never
completes.

## Deploy Checklist

1. Set `FRONT_WEBHOOK_SECRET` in the deployment environment.
2. Keep `ALLOW_UNSIGNED_FRONT_WEBHOOKS=false` in production.
3. Confirm every required attachment hostname is explicitly allowlisted.
4. Review count, byte, and text limits for the deployment's expected traffic.
5. Run the verification commands below before restarting the service.
6. Stop the old process gracefully and allow up to 60 seconds for active scheduler jobs to finish.
7. Send one signed test webhook and confirm `/health` and service logs after deployment.
8. Monitor `dead_letter`, `failed_needs_review`, and provider-side duplicate writes; Front Rule Webhooks do not automatically retry failed deliveries.

## Verification

The repository tests are standalone Python scripts; `pytest` is not required.

```bash
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_linear_ticket_deduplication.py
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent services tasks tools webhooks routes tests config.py main.py models.py
.venv/bin/python -m pip check
git diff --check
```

These tests are offline and do not call the live Front or LLM APIs. A signed
webhook smoke test is still required after deployment.
