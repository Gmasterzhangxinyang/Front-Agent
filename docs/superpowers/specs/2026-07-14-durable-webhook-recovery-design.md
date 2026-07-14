# Durable Front Webhook Recovery Design

## Goal

Guarantee that an authenticated Front webhook is recoverable after it reaches
Front-Agent, even when the Front API, model provider, network, or email handler
fails temporarily.

The normal path must remain immediate: persist the event first, then process it
in the same request. Background retry is a recovery path, not the default
delivery path.

## Constraints

- Keep the current single-process FastAPI, SQLite, and APScheduler deployment.
- Do not add Redis, Celery, or another service.
- Preserve `webhook_events` as the record of successfully handled or
  deterministically ignored Front events.
- Preserve existing `conversation_actions` side-effect idempotency.
- Reuse the current global webhook semaphore and per-conversation locks.
- Do not change classification, skill behavior, Ops pages, or report metrics.
- Preserve the user's current uncommitted scheduler, routing-test, and Ops work.

## Approaches Considered

### 1. Dedicated inbox table (selected)

Add a `webhook_inbox` table for delivery lifecycle state and leave
`webhook_events` unchanged. This makes pending work, successful processing, and
operational reporting unambiguous.

### 2. Extend `webhook_events`

This requires fewer model classes but changes the table from a successful-event
ledger into a mixed queue and ledger. Existing Ops counts would then include
pending and failed deliveries unless every query were changed.

### 3. External queue

Redis plus a worker framework would support horizontal scaling and stronger
distributed coordination. It adds deployment and monitoring complexity that is
not justified for the current single-instance service.

## Architecture

### Inbox Record

Add a `WebhookInbox` model with these fields:

- `event_id`: stable primary key. Use Front's `id` or `event_id`; if both are
  missing, derive `sha256:<hex digest>` from the verified raw request body.
- `conversation_id`: indexed Front conversation ID.
- `payload`: JSON body required for processing and retry.
- `status`: indexed state, one of `pending`, `processing`, `retry`,
  `processed`, or `dead_letter`.
- `attempts`: number of successfully claimed processing attempts.
- `available_at`: earliest time a pending or retry record can be claimed.
- `lease_token`: unique ownership token for the current claim.
- `lease_expires_at`: time after which an abandoned processing claim is
  recoverable.
- `last_error`: bounded diagnostic summary.
- `created_at`, `updated_at`, and `processed_at`: lifecycle timestamps.

`Base.metadata.create_all()` creates the new table on startup, matching the
repository's current schema-management pattern. No existing table is altered.

### Module Boundaries

Create `services/webhook_inbox.py` for persistence and state transitions. Its
public operations are:

- derive a stable event ID;
- insert an event if it does not already exist;
- atomically claim one event with a lease token;
- list due event IDs in a bounded batch;
- mark a claimed event processed and clear its payload;
- schedule a claimed event for retry;
- move an exhausted event to `dead_letter`.

Keep payload interpretation and email handling in
`webhooks/front_webhook.py`. The route remains responsible for signature
verification, request validation, immediate processing, and HTTP semantics.

Add one APScheduler wrapper in `tasks/scheduler.py`. It calls the webhook retry
entry point every minute with `coalesce=True` and `max_instances=1`.

## Request Flow

1. Read the raw request body and verify `X-Front-Signature` exactly as today.
2. Parse JSON and extract the conversation ID.
3. For any conversation-bearing event, derive its stable event ID and commit
   the inbox record before calling Front, the model provider, or any tool.
4. Claim the record for immediate processing.
5. Enter the existing global semaphore and per-conversation lock.
6. Recheck `webhook_events`, then run the existing inbound-message filter,
   allowed-inbox check, and `handle_email` flow.
7. On success or a deterministic ignore outcome, write `webhook_events`, mark
   the inbox record `processed`, and replace its payload with an empty object.
8. On a retryable failure, save the retry state before returning HTTP 503.

If persistence fails, the route returns HTTP 503 and does not start processing.
If a duplicate delivery arrives, the unique event ID prevents a second inbox
row. A currently leased or not-yet-due event remains queued rather than being
processed concurrently.

Events without a conversation ID retain the current immediate ignored response
because they cannot enter the email-processing flow.

## Claim and Concurrency Rules

Claims use a conditional update and inspect the affected-row count. A claim is
valid only when the record is due in `pending` or `retry`, or when a
`processing` lease has expired. Claiming:

1. changes the state to `processing`;
2. increments `attempts`;
3. writes a new random lease token;
4. sets a 15-minute lease expiry.

Completion and failure updates require the same lease token. A stale worker
therefore cannot overwrite the result of a later recovery claim. The existing
webhook semaphore limits total work, and the conversation lock prevents two
events for one conversation from running simultaneously within the process.

The lease is deliberately longer than the usual handler duration. If a handler
runs beyond the lease during a severe outage, existing event and action ledgers
remain the final protection against duplicate successful side effects.

## Retry and Terminal States

The first immediate attempt counts as attempt 1. Failed events use these delays
before attempts 2 through 6:

```text
1 minute, 5 minutes, 15 minutes, 60 minutes, 180 minutes
```

After attempt 6 fails, mark the event `dead_letter`. Do not call external
services again automatically.

Retryable failures include:

- Front request exceptions and transient Front status codes;
- model-provider or network failures surfaced by the handler;
- unexpected handler exceptions;
- unexpected processing exceptions around the existing flow.

Successful terminal outcomes include:

- email handling completes;
- the event is not an inbound customer message;
- the conversation is outside the allowed inboxes;
- `webhook_events` already contains the event ID.

The current handler-error cleanup remains best effort: notify Bobby through the
deduplicated tool path, reopen the conversation, and save
`failed_needs_review`. The queue additionally records the bounded error. A
`dead_letter` transition emits a high-severity structured log with event and
conversation IDs. It does not add a new notification channel or modify Ops.

## Data Retention

Processed inbox rows keep only metadata. Their payload is immediately replaced
with `{}` to avoid retaining email content after recovery is no longer needed.

`pending`, `processing`, `retry`, and `dead_letter` records retain the payload
so they remain recoverable or inspectable. Automatic deletion and an operator
replay UI are outside this change.

## Scheduler Behavior

Every minute, the scheduler fetches at most 20 due event IDs and processes them
through the same claim and webhook-processing entry point used by the immediate
request path. Events are handled sequentially within this job; HTTP webhook
requests may still use the remaining capacity allowed by the shared semaphore.

An exception for one event is logged and does not stop the rest of the batch.
APScheduler uses `coalesce=True`, `max_instances=1`, and the existing Shanghai
timezone configuration.

## Testing

Add standalone offline tests compatible with the repository's current test
runner. They cover:

- stable hash IDs for payloads without a Front event ID;
- duplicate enqueue without payload or attempt corruption;
- inbox commit occurs before the handler starts;
- successful processing writes `webhook_events`, marks `processed`, and clears
  payload;
- a retryable failure returns HTTP 503 and stores the correct next retry time;
- the five retry delays and final `dead_letter` transition;
- only due records can be claimed;
- an active lease cannot be claimed twice;
- an expired lease is recoverable;
- a stale lease token cannot finalize a newer claim;
- deterministic ignored events become terminal;
- the scheduler is registered at a one-minute interval with one instance;
- existing handler-failure, routing, skill, and draft-adoption behavior remains
  unchanged.

No test may call the real Front, model, Linear, or Feishu APIs.

Run the full repository verification set:

```bash
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent services tasks tools webhooks tests config.py main.py models.py
.venv/bin/python -m pip check
git diff --check
```

## Documentation

Update README, `docs/runtime-boundaries.md`, `CLAUDE.md`, and `record.md` so
they describe persistence-before-processing, internal automatic retry, the
retry schedule, dead letters, and the new verification command. Do not claim
that Front itself retries Rule Webhooks.

## Success Criteria

- A valid conversation webhook is durably stored before external processing.
- A process crash or temporary dependency failure does not silently lose the
  event.
- Normal successful mail continues to be processed immediately.
- A duplicated delivery or competing scheduler run cannot claim an active
  event twice.
- Failed events retry no more than five times after the immediate attempt.
- Exhausted events remain visible as `dead_letter` without infinite retries.
- Successful inbox payloads are not retained.
- Existing Ops webhook metrics retain their current meaning.
- All offline regression tests pass without external API access.
