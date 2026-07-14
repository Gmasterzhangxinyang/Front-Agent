# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MANDATORY: After every session

**After making any changes, you MUST append an entry to `record.md` describing what was changed.** Format:

```
## YYYY-MM-DD
- [fix/feat/refactor] description of change (file changed)
```

Never skip this step.

## Running the server

```bash
./start.sh
# Or manually:
source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
```

Server is self-hosted on a cloud VM (124.220.5.97). PORT is set via .env (default 8080).

## Architecture

FastAPI app that receives Front webhook events, classifies emails with an OpenAI-compatible LLM, applies deterministic routes, and otherwise handles them through a constrained skill-based agent loop.

**Entry points:**
- `webhooks/front_webhook.py` - receives and verifies new email events from Front
- `routes/ops.py` - exposes the operations dashboard, reporting API, and authenticated Sybil soft dismissal

**Core flow:**
1. Verify the Front signature and commit valid conversation events to `webhook_inbox`
2. Claim and process the inbox row immediately in the request path
3. Classify email using `skills/classify.md` via the configured LLM provider
4. Apply deterministic routing or load the matching skill from `skills/<category>.md`
5. Run the agent loop with allowlisted function calling
6. Validate model tool arguments and bind trusted conversation/sender context
7. Agent calls tools (Front drafts, Linear tickets, Feishu notifications)
8. Save conversation state and deduplicated action results
9. Let APScheduler retry due or abandoned inbox rows every minute

Education and billing are the explicit multi-turn categories. Billing invoice
correction replies may advance from information collection to Credit Note
acceptance, but `manual_review` is a hard stop for automation. The agent has no
billing-provider tool and must never claim a Credit Note was issued. Follow
`docs/billing-invoice-corrections.md` for the human billing procedure and reply
templates.

**Key files:**
- `agent/orchestrator.py` — classification + agent loop
- `agent/tool_registry.py` — tool schemas and execution
- `tools/front.py` — Front API (drafts, replies, assign, tag)
- `tools/feishu.py` — Feishu text and webhook delivery helpers
- `tools/sybil_digest.py` — queued Sybil handoff digest sender
- `tools/linear.py` — Linear ticket creation
- `skills/*.md` — per-category handling instructions for the agent
- `models.py` — conversation state, action log, webhook inbox/event, and queue models
- `services/webhook_inbox.py` — durable webhook claims, leases, retries, and terminal cleanup
- `services/ops_metadata.py` — bounded Front metadata enrichment for missing Ops sender/summary fields
- `database.py` — async SQLite session
- `config.py` — settings from env vars

**Idempotency rules:**
- `webhook_inbox` durably stores each authenticated conversation event before processing, keyed by Front event ID or a deterministic body hash.
- `webhook_events` deduplicates successful Front webhook deliveries by event ID.
- `conversation_actions` deduplicates successful drafts and handoffs by conversation plus action-specific content. Linear tickets use trusted sender plus normalized original-message content across conversations for 24 hours, with an in-process concurrency lock.
- `webhook_events` is written only after successful processing or deterministic ignore; retryable failures are not recorded as processed.
- Front Rule Webhooks do not retry failed deliveries. Internal APScheduler recovery runs every minute with 1/5/15/60/180-minute delays after the immediate attempt.
- Claims start only after the conversation lock and global webhook capacity are acquired, then use a 15-minute lease. Failed attempt 6 becomes `dead_letter`; processed payloads are cleared while dead-letter payloads remain for manual recovery.
- Recovery is at-least-once: a crash after an external provider accepts a write but before the local action/event commit can repeat that write. Do not claim exactly-once behavior without provider idempotency or reconciliation.
- FastAPI shutdown pauses APScheduler and waits up to 60 seconds for jobs started by this process, reducing the planned-deploy crash window.

## Runtime security boundaries

- `FRONT_WEBHOOK_SECRET` is required at startup by default.
- `ALLOW_UNSIGNED_FRONT_WEBHOOKS=true` is permitted only for local fixtures.
- LLM-originated tool calls are schema validated; trusted conversation and sender context override model values.
- Front attachment credentials are sent only to exact HTTPS hosts in `FRONT_ATTACHMENT_ALLOWED_HOSTS`.
- Attachment count, bytes per file, and extracted text are bounded by settings.
- Unexpected handler failures return HTTP 503, are not recorded in `webhook_events`, and remain queued for internal recovery; `failed_needs_review` can re-enter classification on retry.
- `OPS_WRITE_SECRET` protects Ops mutations. Sybil dismissal changes only `pending` to `dismissed`, retains the row and audit action, and must use HTTPS remotely.
- The digest claims pending Sybil rows as `sending` before network I/O, so in-flight sends cannot be reported as dismissed.
- Operational details and deploy checks are in `docs/runtime-boundaries.md`.

## Verification

Run all standalone checks before commit or deploy:

```bash
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_linear_ticket_deduplication.py
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_ops_sybil_dismissal.py
.venv/bin/python tests/test_ops_data_quality.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent services tasks tools webhooks routes tests config.py main.py models.py
.venv/bin/python -m pip check
git diff --check
```

## Environment variables (set in .env)

`FRONT_API_TOKEN`, `FRONT_WEBHOOK_SECRET`, `ALLOW_UNSIGNED_FRONT_WEBHOOKS`, `FRONT_ATTACHMENT_ALLOWED_HOSTS`, `MAX_ATTACHMENT_COUNT`, `MAX_ATTACHMENT_BYTES`, `MAX_ATTACHMENT_TEXT_CHARS`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_SYBIL_OPEN_ID`, `FEISHU_EDUCATION_GROUP_CHAT_ID`, `FEISHU_WEBHOOK_BOBBY`, `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_CUS_PROJECT_ID`, `OPS_WRITE_SECRET`, `PORT`
