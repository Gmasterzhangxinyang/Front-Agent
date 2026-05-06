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
uvicorn main:app --reload --port 8000
```

Deployed on Railway (auto-deploy from GitHub `main` branch). Push to main to deploy.

## Architecture

FastAPI app that receives Front webhook events, classifies emails with GPT-4o, and handles them via a skill-based agent loop.

**Entry points:**
- `webhooks/front.py` — receives new email events from Front
- `webhooks/feishu_card.py` — receives button-click callbacks from Feishu interactive cards

**Core flow:**
1. Front webhook → `agent/orchestrator.py:handle_email()`
2. Classify email using `skills/classify.md` via GPT-4o
3. Load matching skill from `skills/<category>.md`
4. Run agent loop (`_run_agent_loop`) with GPT-4o function calling
5. Agent calls tools (Front drafts, Linear tickets, Feishu notifications)
6. Bobby clicks Feishu card buttons → `webhooks/feishu_card.py` handles actions

**Key files:**
- `agent/orchestrator.py` — classification + agent loop
- `agent/tool_registry.py` — tool schemas and execution
- `tools/front.py` — Front API (drafts, replies, assign, tag)
- `tools/feishu.py` — Feishu card builders and send/update
- `tools/linear.py` — Linear ticket creation
- `skills/*.md` — per-category handling instructions for the agent
- `models.py` — `ConversationState` SQLAlchemy model
- `database.py` — async SQLite session
- `config.py` — settings from env vars

**Feishu card flow:**
- Cards are sent via `feishu.send_card()`, message_id stored for updates
- Feishu sends TWO callbacks per button click: old format + schema 2.0 — both are handled in `feishu_card.py`
- Card updates use `feishu.update_card(message_id, new_card)`

**Agent deduplication rules (already implemented):**
- `feishu_notify_bobby` is deduplicated per conversation per agent loop run (only first call goes through)
- `resolved` action is deduplicated via `_check_and_set_resolved()` to prevent double closing drafts

## Environment variables (set in Railway)

`FRONT_API_TOKEN`, `OPENAI_API_KEY`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_BOT_CHAT_ID`, `FEISHU_WEBHOOK_BOBBY`, `FEISHU_WEBHOOK_YONGLE`, `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, `LINEAR_PROJECT_ID`
