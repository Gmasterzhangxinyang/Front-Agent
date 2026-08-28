# Front-Agent

Front-Agent is the production support-mailbox automation service for Dify. It accepts trusted Front events, builds a bounded conversation context, classifies each request, applies deterministic Python routing where possible, and runs a constrained category Skill for everything else.

> Safety default: customer-facing content is created as a Front draft. The LLM cannot send customer email directly or call arbitrary APIs.

## Start Here

| Resource | Best for |
|---|---|
| [Interactive overview](docs/front-support-architecture.html) | Fast system orientation: trusted intake, decisions, tools, state, recovery |
| [Interactive full architecture](docs/front-support-full-architecture.html) | Guided inspection of trust, memory, policy, integrations, scheduler, and Ops |
| [Architecture hub](docs/current-system-architecture.md) | Reading order, guarantees, limitations, and source ownership |
| [Stages ①–⑧](docs/current-system-architecture-details.md) | Detailed ingress-to-recovery walkthroughs with source diagrams |
| [Runtime boundaries](docs/runtime-boundaries.md) | Security, retries, side-effect semantics, and deployment checks |
| `/ops/system-flow` | Login-protected live email journey with runtime telemetry |

## Runtime Snapshot

| Area | Current behavior |
|---|---|
| Entry | FastAPI `POST /webhook/front` with Front HMAC-SHA1 signature verification |
| Decision space | 16 categories and 52 sub-types; confidence is observability only |
| Policy | Deterministic Python routes first, then one category Skill |
| Tools | 20 allowlisted tools with schema validation and trusted-context rebinding |
| State | Async SQLAlchemy over SQLite: conversation state, actions, webhook recovery, queues, reports |
| Background work | APScheduler retries, reports, metadata refresh, stale close, digest, and reply-SLA checks |
| Production process | `screen` session `front-agent-v2`, port `8080`, release directories under `/tmp/front-agent-release-*` |

## Core Guarantees

- Signed conversation events are committed to `webhook_inbox` before processing.
- Only real external inbound messages in the Support inbox enter the primary automation path.
- Customer replies are draft-first; direct customer-send tools are blocked.
- Conversation IDs, original senders, and draft recipients are rebound from trusted runtime context.
- Attachments require exact Front-managed HTTPS hosts and hard count, byte, and text limits.
- Clear spam may be archived deterministically; every other route stays open for review or follow-up.
- Linear creation uses exact dedupe first, then a bounded same-sender 24-hour semantic review; uncertainty creates a new issue.
- `dify_lookup_billing` is read-only, uses fixed queries, and is bound to the trusted Front sender.
- Durable recovery is at-least-once, not exactly-once; provider acceptance before local commit can still repeat an external write.

## Request Lifecycle

`Front Rule Webhook → verify → durable inbox → trusted context → classify → route/Skill → safe tool → state/action log`

| Stage | Responsibility | Primary code |
|---|---|---|
| 1. Trust | Verify signature, JSON, event identity, and conversation identity | `webhooks/front_webhook.py` |
| 2. Persist | Commit the authenticated event and claim it with a lease | `services/webhook_inbox.py` |
| 3. Context | Load thread, bounded attachments, state, same-sender history, and Case Memory | `agent/orchestrator.py` |
| 4. Classify | Produce category, sub-type, evidence, flags, and secondary intents | `agent/classification.py`, `skills/classify.md` |
| 5. Route | Prefer deterministic spam, inbox, legal, partnership, and manual-review rules | `agent/routing.py` |
| 6. Policy | Load the selected category Skill and multi-turn state | `skills/*.md` |
| 7. Execute | Validate tools, rebind trusted arguments, dedupe, and call providers | `agent/tool_registry.py` |
| 8. Commit/recover | Save state and actions; complete, retry, or dead-letter the webhook | `tools/state.py`, `services/webhook_inbox.py` |

Two layers decide behavior:

- `agent/routing.py` owns deterministic routes for spam, unclear, security, business, marketing, partnership, and legal.
- `skills/*.md` through `agent/orchestrator.py` owns variable workflows such as education, account, technical, billing, purchase, roadmap, data export, and investment.

## Operational Automation

| Job | Schedule and boundary |
|---|---|
| Webhook recovery | Every minute; 1/5/15/60/180-minute delays, 15-minute lease, attempt 6 becomes `dead_letter` |
| Reply SLA | Every 15 minutes on China-time weekdays; union of all open Support conversations and all open conversations assigned to Bobby |
| SLA eligibility | Only customer emails received on or after 2026-08-28 00:00 China time; older backlog is permanently ignored |
| SLA suppression | A later real customer-facing reply or Bobby-authored Front comment; drafts and API-bot comments do not count |
| Ops metadata | Every 15 minutes, bounded blank-field enrichment without overwriting existing sender/summary data |
| Ops reports | At startup and every 3 hours; daily, weekly, and monthly snapshots |
| Sybil handoff | Queued digest instead of direct email to Sybil |

Technical support remains Skill-driven because requests vary widely. It requires Docs/GitHub grounding when relevant and still produces drafts by default.

## Case Memory

`services/case_memory.py` retrieves similar historical rows from `conversation_states` and formats them as `Historical case memory / hindsight signals` prompt context before classification and before category skill execution.

Safety constraints:

- Matching is conservative: classification context requires at least 3 effective token overlaps; known-category skill context requires at least 2.
- Category and previous outcome only affect ranking after the overlap threshold is met; they cannot create a match by themselves.
- Each prompt item includes `match=` retrieval evidence so the model can ignore weak or irrelevant memories.
- Matched cases are separated into `Successful patterns` and `Cautionary patterns` rather than copied as raw history.
- Generic terms such as `support`, `issue`, `question`, and `request` are ignored.
- Email addresses and phone numbers are redacted before entering the prompt.
- Case memory is reference-only. Deterministic routing, tool allowlists, draft-only policy, and skill safety rules still win.
- Case memory does not replace documentation matching. Technical/docs grounding still comes from skill instructions and tools such as `docs_search` and `github_search`.

## Deterministic Routes

| Classification | Route | Tool/action | State |
|---|---|---|---|
| `spam` / clear ads | `spam_auto_close` | archive conversation | `closed_spam` |
| `unclear` | `manual_review_bobby` | forward to `bobby@dify.ai` | `manual_review` |
| `security` | `security_move_inbox` | move to Front inbox `Security` | `moved_inbox` |
| `business` / enterprise / procurement | `business_move_inbox` | move to Front inbox `Business` | `moved_inbox` |
| `marketing` | `marketing_move_inbox` | move to Front inbox `Marketing` | `moved_inbox` |
| `partnership` / marketplace / community / technology integration | `partnership_forwarded_keep_open` | forward to `marketing@dify.ai` | `forwarded_keep_open` |
| `legal` or `legal_threat` flag | `legal_forwarded_keep_open` | forward to `geyan@dify.ai` | `forwarded_keep_open` |
| everything else | `*_skill_flow` | load `skills/<category>.md` | skill decides |

`confidence` is observability only. It must not control routing with a numeric threshold.

## Tool Safety

LLM cannot call arbitrary APIs. It can only call schemas in `agent/tool_registry.py`.

Important constraints:

- LLM tool names and arguments are validated against the registered schema.
- Conversation IDs are rebound to the trusted webhook context before execution.
- Draft recipients are forced to the original sender immediately before the Front side effect.
- `dify_lookup_billing` is read-only, uses fixed SQL, and is rebound to the trusted Front sender; the model cannot query another email or access the generic DB Gateway SQL tool.
- No generic `front_forward` tool is exposed.
- `front_close_conversation` is not exposed to the LLM; only deterministic spam can close.
- Deprecated direct reply tools are blocked.
- `front_create_draft` creates a Front draft only.
- Internal handoffs use dedicated `front_forward_to_*` tools.
- Internal recipients are restricted to `@dify.ai` where applicable.
- Handler exceptions notify Bobby through the deduplicated action log, explicitly reopen the original conversation, save `failed_needs_review`, do not mark the webhook event processed, and return HTTP 503 instead of a false success. The inbox row remains durable for internal retry.

## Idempotency and Original Sender Guard

There are two idempotency layers plus a durable recovery queue:

| Layer | Table | Key | Purpose |
|---|---|---|---|
| Recovery | `webhook_inbox` | Front `event_id` or deterministic body hash | persist authenticated conversation events before processing |
| Webhook | `webhook_events` | Front `event_id` | skip duplicate webhook deliveries |
| Tool side effects | `conversation_actions` | tool-specific scope + content hash | skip duplicate successful writes |

Normal handling still starts immediately in the HTTP request path. APScheduler
checks the durable inbox every minute because Front Rule Webhooks do not retry
failed deliveries. After the immediate attempt, failures wait 1, 5, 15, 60,
and 180 minutes. A failed attempt 6 becomes `dead_letter` and is logged for
manual review. Claims use a 15-minute lease so a process crash does not leave a
row permanently stuck in `processing`.

Successful processing clears the stored payload. Dead-letter rows retain their
payload and bounded diagnostic for manual recovery. `webhook_events` remains
the downstream idempotency ledger and records only successful or
deterministically ignored events, never retryable failures. Claims begin only
after the worker has the conversation lock and global execution capacity, so
queue wait time does not consume the lease.

Recovery provides at-least-once processing, not exactly-once external side
effects. If Front, Linear, or another provider accepts a write and the process
exits before the local `conversation_actions` or `webhook_events` commit, a
retry can repeat that write. Graceful scheduler shutdown waits up to 60
seconds for active jobs, reducing this window during planned deploys. Provider
idempotency or reconciliation is still needed for an exactly-once guarantee.

`conversation_actions` covers duplicate-prone writes:

| Tool | Action key |
|---|---|
| `front_create_draft` | normalized draft body hash |
| `front_add_comment` | normalized internal comment body hash |
| `linear_create_ticket` | exact trusted sender + message hash, then conservative same-sender semantic review within 24 hours |
| `feishu_notify_sybil_group` / `front_forward_to_sybil` | handoff type + Linear URL, or message hash |
| `front_forward_to_bobby` / `front_forward_to_limin` / other internal forwards | summary/message hash |

Linear ticket deduplication is the exception to conversation-only scope: two
conversations from the same trusted sender share an in-process sender lock. An
exact normalized-message match reuses the first successful ticket immediately.
Otherwise, the runtime inspects up to five same-sender tickets from the previous
24 hours, applies a lexical suspicion gate, and asks the configured LLM for a
conservative duplicate decision. Only `duplicate=true` with high confidence
reuses the existing ticket. A negative, uncertain, malformed, or failed review
creates a new ticket. Model-supplied sender/message values cannot change the
trusted key or select the ticket to reuse. Other actions remain
conversation-scoped, so new information can still produce a materially
different draft or handoff.

`conversation_states.sender_email` stores the original customer sender once known and is not overwritten by later internal forwards. `front_create_draft` receives this sender from Python so internal Bobby handoff messages cannot make drafts target `bobby@dify.ai`.

Every external customer email, whether it starts a new Front conversation or continues an existing one, loads up to five other recent conversations for the same normalized email address. The runtime combines Front contact conversation discovery with local state, excludes unsent drafts from transcripts, and supplies subjects, sent exchanges, workflow state, and existing Linear metadata to classification and skill handling so related threads are reconciled before taking another action.

## Skills

Business rules live in `skills/`. Update a skill when changing classification examples, draft wording, or category policy. Update Python only for deterministic routes, new tools, or safety boundaries.

| Skill | Purpose |
|---|---|
| `classify.md` | classification JSON schema, examples, routing-oriented rules |
| `technical.md` | technical drafts, docs/GitHub grounding, paid/non-paid handling |
| `account.md` | login, deletion, transfer, email change, account anomaly, hacked account |
| `billing.md` | refund, duplicate charge, invoice, downgrade/cancel drafts; existing-invoice Credit Note confirmation |
| `education.md` | education review, Sybil digest handoff, proof requests |
| `purchase.md` | pricing, Enterprise contact guidance, reseller routing |
| `business.md` | documents deterministic Business inbox behavior |
| `partnership.md` | marketplace/community/plugin cooperation to marketing |
| `legal.md` | legal handoff to Geyan, no customer reply |
| `security.md` | security inbox behavior |

Reply-producing skills include a `Draft Quality Bar`: do not invent facts, do not mention internal tools or people, ask for missing facts, and avoid promises not proven by tool results or policy.

## State Model

SQLite models are in `models.py` and initialized by `database.py`.

| Table | Purpose |
|---|---|
| `conversation_states` | category, sub_type, step, waiting, payload, original sender |
| `conversation_actions` | tool-level action log and dedupe |
| `webhook_inbox` | durable authenticated webhook payloads, leases, retries, and dead letters |
| `webhook_events` | Front event idempotency |
| `sybil_notifications` | pending/sending/sent/dismissed Sybil digest queue; dismissed rows remain retained |

Important steps:

| Step | Meaning |
|---|---|
| `awaiting_*` | waiting for user information |
| `draft_created` | Front draft created for review |
| `forwarded_keep_open` | internal handoff sent, conversation remains open |
| `manual_review` | Bobby review required |
| `moved_inbox` | moved to another Front inbox |
| `failed_needs_review` | tool or handler did not safely complete |
| `closed_spam` | deterministic spam route archived |

Existing-invoice correction requests create a draft explaining that already-issued
invoices cannot be changed or reissued, politely asking the customer to update and
verify Billing Info in the portal for future invoices, and asking whether the
customer wants a supplementary Credit Note for the existing invoice.
Only an explicit second customer reply while in
`awaiting_credit_note_confirmation` adds a deduplicated internal Front comment
stating that the case should go to Elsie; it does not assign the conversation,
create a ticket, enter an Ops queue, or perform the Credit Note action.

## Code Map

```text
main.py                    FastAPI app, DB init, scheduler
config.py                  pydantic-settings config
database.py                SQLAlchemy async engine/session
models.py                  ORM models
start.sh                   local start script
railway.toml               optional Railway config
agent/orchestrator.py      main processing loop and skill execution
services/case_memory.py    conservative historical case-memory prompt context
services/ops_metadata.py   conservative Front metadata backfill for Ops rows
services/webhook_inbox.py   durable Front event claims, leases, retries, dead letters
services/unanswered_reminders.py  weekday 12-hour reply-SLA scanner
agent/classification.py    classification parsing/normalization
agent/routing.py           deterministic routes
agent/tool_registry.py     allowlisted tool schemas and dispatch
tools/front.py             Front API wrapper
tools/dify_billing.py      trusted-sender, fixed-query, read-only billing lookup
tools/feishu.py            Feishu app messaging and personal reminders
tools/handoff.py           internal handoff helpers
tools/linear.py            Linear ticket creation
tools/state.py             state/action log helpers
tools/sybil_digest.py      Sybil digest queue and sender
webhooks/front_webhook.py  Front webhook boundary
routes/ops.py             Ops dashboard API and /ops page
routes/static/ops.html    Ops dashboard frontend
skills/                    business policy and draft instructions
tests/                     routing and skill safety tests
```

## Configuration

Use `.env.example` as the template. Do not commit real secrets.

```bash
FRONT_API_TOKEN=
FRONT_WEBHOOK_SECRET=
# Local development only. Keep false in production.
ALLOW_UNSIGNED_FRONT_WEBHOOKS=false
FRONT_APP_BASE_URL=https://app.frontapp.com/open
FRONT_ATTACHMENT_ALLOWED_HOSTS=api2.frontapp.com
MAX_ATTACHMENT_COUNT=5
MAX_ATTACHMENT_BYTES=10485760
MAX_ATTACHMENT_TEXT_CHARS=50000

OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.chat/v1

FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BOBBY_EMAIL=bobby@dify.ai
FRONT_TEAMMATE_BOBBY=tea_hg6jf

LINEAR_API_KEY=
LINEAR_TEAM_ID=
LINEAR_CUS_PROJECT_ID=

INTERNAL_FORWARD_BOBBY_EMAIL=bobby@dify.ai
INTERNAL_FORWARD_LIMIN_EMAIL=bobby@dify.ai
INTERNAL_FORWARD_SYBIL_EMAIL=sybil@dify.ai
MARKETING_PARTNERSHIP_EMAIL=marketing@dify.ai
MARKETING_INBOX_NAME=
SECURITY_INBOX_NAME=Security
BUSINESS_INBOX_NAME=Business
GEYAN_EMAIL=geyan@dify.ai
CLAUDIA_EMAIL=

DATABASE_URL=sqlite+aiosqlite:///./email_automation.db
DIFY_DB_MCP_URL=https://zendesk.smlershou.top/db-gateway/mcp
DIFY_DB_MCP_TOKEN=
DIFY_DB_MCP_TIMEOUT_SECONDS=20
ENABLE_SCHEDULER=true
OPS_ADMIN_USERNAME=
OPS_ADMIN_PASSWORD=
OPS_SESSION_HOURS=12
OPS_COOKIE_SECURE=false
PORT=8000
```

`FRONT_WEBHOOK_SECRET` is the API secret shown by Front's Webhooks app, not the
Front API token. It is required by default. For local webhook fixtures only,
set `ALLOW_UNSIGNED_FRONT_WEBHOOKS=true`; never enable it in production.
`FRONT_ATTACHMENT_ALLOWED_HOSTS` must contain only exact Front-managed HTTPS
hosts used by the deployment. Attachment count, byte, and text limits bound
memory use and model prompt growth.
`DIFY_DB_MCP_TOKEN` enables the optional read-only billing lookup. Keep it only
in the runtime secret environment. The agent maps the trusted Front sender to a
Dify tenant through fixed queries and returns a minimized subscription/quota
snapshot; it never exposes arbitrary SQL to the model.

`OPS_ADMIN_USERNAME` and `OPS_ADMIN_PASSWORD` are required at startup and
protect the entire Ops page and every `/ops/api/*` data endpoint. Successful
login creates a process-local, revocable HttpOnly session with the lifetime set
by `OPS_SESSION_HOURS`. Set `OPS_COOKIE_SECURE=true` only when Ops is served
through HTTPS. Mutations also require the same-origin `X-Ops-Request` header.
The education exception dismissal changes only a `pending` row to `dismissed`;
`sent` rows remain immutable and dismissed rows remain visible for audit.
Use HTTPS for any remote login so credentials are not transmitted in plaintext.

See [Runtime Security and Retry Boundaries](docs/runtime-boundaries.md) for
deployment checks, failure semantics, and the exact verification commands.

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
bash start.sh
curl http://localhost:8000/health
```

Production-like local screen currently uses port `8080` and release directories under `/tmp/front-agent-release-*`.

## Optional Railway Deploy

`railway.toml` exists for Railway, but the active local deployment in this workspace is the `front-agent-v2` screen process. If using Railway, configure environment variables in Railway and point Front webhook to the Railway public URL.

## Change Checklist

Run before commit/deploy:

```bash
.venv/bin/python tests/test_dify_db_tool.py
.venv/bin/python tests/test_webhook_recovery.py
.venv/bin/python tests/test_linear_ticket_deduplication.py
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_ops_sybil_dismissal.py
.venv/bin/python tests/test_ops_auth.py
.venv/bin/python tests/test_ops_data_quality.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python tests/test_unanswered_reminders.py
.venv/bin/python -m compileall -q agent services tasks tools webhooks routes tests config.py main.py models.py
.venv/bin/python -m pip check
git diff --check
```

The tests are offline. After deployment, send a signed Front webhook as a live
smoke test; the repository suite does not call Front or the configured LLM.

## Maintenance Notes

- Do not commit `.env`, SQLite DB files, screen logs, virtualenvs, or generated caches.
- `screenlog.*` is runtime log output, not source.
- Production state should use a persistent SQLite path or external DB.
- Ops dashboard is available at `/ops` only after administrator login. The same session protects every Ops API, and mutations additionally require a same-origin write header. Its overview separates actionable failures and queues from historical data gaps. It does not edit skills or send customer messages.
- Every 15 minutes, at most 20 missing conversation rows are enriched from Front, with actionable rows first and a 60-second run limit. The job only fills blank original sender and subject-derived summary fields, preserves the business activity timestamp, and never overwrites existing values.
- Ops report snapshots are generated once when the scheduler starts, then every 3 hours. Each run stores both `daily` and `monthly` reports in `ops_reports`; the dashboard reads the latest snapshot for the selected period.
