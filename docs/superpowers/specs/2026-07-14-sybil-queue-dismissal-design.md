# Sybil Queue Manual Dismissal Design

## Goal

Allow an operator to remove one pending Sybil notification from the outgoing
digest through the Ops dashboard without deleting its database record.

The operation must be authenticated, auditable, and limited to notifications
that have not already been sent.

## Current Behavior

- `sybil_notifications` stores pending and sent digest entries.
- `send_pending_sybil_digest()` selects only rows whose status is `pending`.
- `/ops/api/sybil` lists queue rows, and the Ops table is currently read-only.
- The Ops read APIs do not require authentication because they have no mutation
  capability.
- `routes/ops.py` and related scheduler tests currently contain unrelated
  uncommitted work that must be preserved.

## Selected Approach

Use a soft dismissal:

- change one row from `pending` to `dismissed`;
- keep the original notification row and message;
- leave `sent` rows immutable;
- record the operator action in the existing `conversation_actions` audit log;
- protect the write endpoint with a dedicated shared secret.

Physical deletion was rejected because it removes operational history. Adding
a new dismissal table or schema columns was rejected because the existing
action log already provides an action timestamp without requiring a migration.

## Status Semantics

The supported queue states become:

- `pending`: eligible for the next Sybil digest;
- `sending`: temporarily claimed by one digest worker under a 30-minute lease;
- `sent`: already included in a successful digest;
- `dismissed`: manually removed before delivery and retained for history.

The digest sender still selects only `pending` rows, but atomically changes each
claimed row to `sending` before network I/O. The lease marker is stored in the
existing `error` field as an expiry plus a unique token, is hidden from Ops API
responses, and must match when the worker records success or failure. Expired or
invalid leases are atomically recovered on the next digest run, so a crashed
worker cannot leave a permanent `sending` row and a stale worker cannot
overwrite a newer claim. A crash after Feishu accepts the digest but before the
local `sent` commit can cause an at-least-once retry after lease expiry; this is
preferable to silently losing the queue when the remote API has no idempotency
key. Dismissed rows remain visible in the Ops table.

## Write Authentication

Add `ops_write_secret: str = ""` to application settings and document the
`OPS_WRITE_SECRET` environment variable.

The real value is stored only in the untracked production `.env`. It must never
be committed, rendered into HTML, returned by an API, or written to logs.
`.env.example` contains only an empty example value.

The dismissal endpoint reads `X-Ops-Write-Secret` and compares it with the
configured secret using `hmac.compare_digest`.

- If the server secret is empty, write operations are disabled with HTTP 503.
- If the header is missing or incorrect, return HTTP 403.
- Read-only Ops routes remain unchanged.

This shared-secret design is intentionally limited to the one requested write
operation. It is not a replacement for full Ops authentication. Production
access should use HTTPS so the header is not exposed in transit.

## API

Add:

```text
DELETE /ops/api/sybil/{notification_id}
X-Ops-Write-Secret: <configured value>
```

Behavior:

1. Authenticate before opening a mutation transaction.
2. Load the `SybilNotification` by integer ID.
3. Return HTTP 404 if it does not exist.
4. If status is `sent`, return HTTP 409 and do not modify it.
5. If status is already `dismissed`, return the row as a successful idempotent
   result.
6. If status is `pending`, set it to `dismissed` and retain every other field.
7. In the same transaction, add one `ConversationAction` with:
   - the notification conversation ID;
   - `action_type="sybil_dismiss"`;
   - `action_key="notification:<id>"`;
   - `result="dismissed"`.
8. Commit and return the serialized notification.

The unique action constraint makes the audit record idempotent. A concurrent
duplicate request that loses the unique-insert race rolls back, reloads the now
dismissed notification, and returns it successfully.

The endpoint never changes the conversation state, Linear issue, Front draft,
or any previously queued action record.

## Ops User Interface

Add an action column to the Sybil table.

- A `pending` row displays a compact `Remove` / `移除` command.
- `sent` and `dismissed` rows display no mutation command.
- Clicking remove first shows a native confirmation containing the conversation
  ID.
- After confirmation, request the write password if it is not already held in
  the current page's JavaScript memory.
- The password is never written to local storage, session storage, the DOM, or
  the page source.
- Send it only in `X-Ops-Write-Secret` to the same-origin endpoint.
- On success, reload the Sybil list and dashboard summary. The same row remains
  visible with status `dismissed`, while pending counts decrease.
- On HTTP 403, clear the in-memory password so the next attempt asks again.
- Display a concise localized error for failed operations.

The status badge uses a neutral style for `dismissed`; `pending` remains a
warning and `sent` remains successful.

## Audit and Metrics

`ConversationAction.created_at` is the dismissal timestamp. The action log
already exposes the action type, conversation ID, result, and time in Ops.

Existing pending metrics count only `status == "pending"` and therefore update
without query changes. Status distributions automatically include a
`dismissed` bucket. Sent metrics remain unchanged.

## Tests

Add offline tests for:

- a missing server secret disables the mutation;
- a missing or incorrect request header returns HTTP 403 without mutation;
- an unknown notification ID returns HTTP 404;
- a pending row becomes `dismissed` but remains in `sybil_notifications`;
- the original message, Linear URL, and conversation ID are unchanged;
- one `sybil_dismiss` action is recorded with the notification ID;
- repeated dismissal is successful and does not add a second audit action;
- a sent row returns HTTP 409 and remains sent;
- an in-flight `sending` row returns HTTP 409 rather than reporting a false dismissal;
- the digest sender still selects pending rows only, conditionally claims them,
  restores ordinary failures, and recovers expired leases;
- the Ops table renders dismissed rows and exposes the remove command only for
  pending rows;
- the browser sends the write secret only as a request header and does not use
  persistent browser storage.

All tests use an isolated SQLite database or source-level UI assertions. They
must not call Front, Feishu, Linear, or any model provider.

Run the full existing routing, runtime-boundary, skill, and draft-adoption test
scripts after the focused test.

## Documentation

Update README, `.env.example`, `CLAUDE.md`, and `record.md` with:

- the new environment variable name, never its real value;
- pending, sending, sent, and dismissed status meanings;
- the authenticated manual dismissal behavior;
- the focused verification command;
- the requirement to use HTTPS for remote Ops write operations.

## Success Criteria

- An operator can dismiss exactly one pending Sybil notification from Ops.
- The notification row remains stored and visible as `dismissed`.
- Dismissed notifications are never sent in a digest.
- Sent notifications cannot be changed.
- An unauthenticated caller cannot mutate the queue.
- The real write secret is absent from tracked files and API responses.
- Each successful dismissal has exactly one audit action.
- Existing Ops, scheduler, and email automation behavior remains unchanged.
