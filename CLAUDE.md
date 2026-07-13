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
- `routes/ops.py` - exposes the read-only operations dashboard and reporting API

**Core flow:**
1. Front webhook → `agent/orchestrator.py:handle_email()`
2. Classify email using `skills/classify.md` via the configured LLM provider
3. Apply deterministic routing or load the matching skill from `skills/<category>.md`
4. Run the agent loop with allowlisted function calling
5. Validate model tool arguments and bind trusted conversation/sender context
6. Agent calls tools (Front drafts, Linear tickets, Feishu notifications)
7. Save conversation state and deduplicated action results

**Key files:**
- `agent/orchestrator.py` — classification + agent loop
- `agent/tool_registry.py` — tool schemas and execution
- `tools/front.py` — Front API (drafts, replies, assign, tag)
- `tools/feishu.py` — Feishu text and webhook delivery helpers
- `tools/sybil_digest.py` — queued Sybil handoff digest sender
- `tools/linear.py` — Linear ticket creation
- `skills/*.md` — per-category handling instructions for the agent
- `models.py` — conversation state, action log, webhook event, and queue models
- `database.py` — async SQLite session
- `config.py` — settings from env vars

**Idempotency rules:**
- `webhook_events` deduplicates successful Front webhook deliveries by event ID.
- `conversation_actions` deduplicates successful drafts, tickets, and handoffs by conversation plus action-specific content.
- Failed webhook handling is not recorded as processed, so Front can retry it.

## Runtime security boundaries

- `FRONT_WEBHOOK_SECRET` is required at startup by default.
- `ALLOW_UNSIGNED_FRONT_WEBHOOKS=true` is permitted only for local fixtures.
- LLM-originated tool calls are schema validated; trusted conversation and sender context override model values.
- Front attachment credentials are sent only to exact HTTPS hosts in `FRONT_ATTACHMENT_ALLOWED_HOSTS`.
- Attachment count, bytes per file, and extracted text are bounded by settings.
- Unexpected handler failures return HTTP 503, are not recorded as processed, and `failed_needs_review` can re-enter classification on retry.
- Operational details and deploy checks are in `docs/runtime-boundaries.md`.

## Verification

Run all standalone checks before commit or deploy:

```bash
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent tools webhooks tests config.py main.py
.venv/bin/python -m pip check
git diff --check
```

## Environment variables (set in .env)

`FRONT_API_TOKEN`, `FRONT_WEBHOOK_SECRET`, `ALLOW_UNSIGNED_FRONT_WEBHOOKS`, `FRONT_ATTACHMENT_ALLOWED_HOSTS`, `MAX_ATTACHMENT_COUNT`, `MAX_ATTACHMENT_BYTES`, `MAX_ATTACHMENT_TEXT_CHARS`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_SYBIL_OPEN_ID`, `FEISHU_EDUCATION_GROUP_CHAT_ID`, `FEISHU_WEBHOOK_BOBBY`, `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_CUS_PROJECT_ID`, `PORT`
