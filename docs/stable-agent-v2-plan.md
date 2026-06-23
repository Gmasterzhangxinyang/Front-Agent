# Stable Agent V2 Engineering Spec

This is the implementation spec for the new stable version of Front-Agent. The currently running `screen` production service must remain unchanged until this spec, code diff, and historical replay results are reviewed and explicitly approved for deployment.

## 1. System Goal

Build a stable support automation system that can classify Front conversations, select a deterministic route, execute only allowed actions, preserve original customer context for internal handoffs, and make every non-spam decision reviewable.

The core architecture change is to stop mixing classification, routing, reply policy, escalation policy, and tool side effects inside one LLM loop.

## 2. Non-Negotiable Safety Rules

- Work only on `refactor/stable-agent-v2` until deployment is approved.
- Do not restart, kill, attach, or replace the currently running production `screen` service during refactor work.
- No Feishu runtime path: no Feishu cards, callbacks, buttons, `已解决`, tenant token, or webhook state workflow.
- No SMTP notification sender.
- Internal handoffs must use Front forwarding only.
- Internal handoff tools must never send email to customers.
- Customer-facing communication must happen only through approved Front customer tools: draft or reply.
- Default customer action is draft or no reply. Direct-send must be explicitly allowed by policy.
- Spam/ads may auto-close only when the route is clearly spam/ads.
- All non-spam handoffs stay open so Bobby can verify routing quality.
- No fixed confidence threshold controls routing. `confidence` is observability only.

## 3. Architecture Layers

```text
Front webhook
  -> signature verification
  -> webhook event idempotency
  -> allowed inbox filter
  -> full conversation and attachment loading
  -> classification layer
  -> routing decision layer
  -> policy/skill layer when needed
  -> tool execution layer with action log dedupe
  -> state persistence and audit comment
```

Current runtime split:

- Python deterministic routing owns high-confidence, high-risk route selection such as spam close, security inbox move, unclear Bobby review, legal handoff, and partnership/marketing routing.
- LLM skill flow still owns complex support workflows such as education/account/technical/billing by selecting from an allowlisted tool set. Tool execution must enforce idempotency and recipient safety because the LLM can retry or repeat a tool call.
- Technical support is currently skill-flow based: the LLM may search docs/GitHub, create Linear tickets when warranted, create Front drafts, and set state. It must not directly send customer replies.

| Layer | File | Responsibility | Must Not Do |
|---|---|---|---|
| Webhook | `webhooks/front_webhook.py` | Verify event, dedupe, filter inbox, call orchestrator | Decide business route |
| Classification | `agent/classification.py` | Parse and normalize LLM JSON | Execute tools or choose recipients |
| Routing | `agent/routing.py` | Convert classification into deterministic route | Write long replies or call APIs directly |
| Orchestration | `agent/orchestrator.py` | Coordinate classification, routing, skill loop, state | Hide routing rules in prompts |
| Tool Registry | `agent/tool_registry.py` | Expose allowed tool schemas, dispatch calls, action-log dedupe | Make classification decisions |
| Front API | `tools/front.py` | Front draft/reply/forward/move/close/comment APIs | Choose business owners |
| Handoff | `tools/handoff.py` | Internal Front forwarding to configured recipients | Send to customer addresses |
| Skills | `skills/*.md` | Category-specific policy and templates | Override global safety rules |

## 4. Classification Contract

The classifier output is not the final action. It is structured evidence for the routing layer.

Required JSON fields:

```json
{
  "category": "technical | account | purchase | education | billing | partnership | marketing | security | spam | legal | roadmap | investment | business | data_export | unclear",
  "sub_type": "string or null",
  "summary": "one sentence summary",
  "sender_email": "sender email",
  "is_paid_user": true,
  "is_premium": false,
  "urgency": "normal | high",
  "flags": [],
  "secondary_intents": [],
  "evidence": ["short evidence phrase"],
  "confidence": 0.0
}
```

Classification rules:

- Advertising, sponsorship, SEO, backlinks, guest posts, lead generation, conference promotion, media package, PR promotion, and unsolicited sales are `spam`.
- Marketplace, plugin, template, and community ecosystem cooperation are `partnership`; they route to `marketing@dify.ai`, not Sherry or 赵雅雯.
- Security vulnerabilities, responsible disclosure, abuse reports, data leaks, active compromise, and security reports are `security`.
- Education plan application, rejection, discount, school eligibility, and education email problems are `education` unless the dominant issue is generic account login.
- Login, verification code, account deletion, account transfer, change email, quota anomaly, blacklist, and account ownership issues are `account`.
- Refund, invoice, duplicate charge, downgrade, and paid subscription cancellation are `billing`.
- If multiple intents exist, choose the highest operational priority as `category` and place others in `secondary_intents`.
- If evidence is insufficient or the route is outside known rules, classify as `unclear`.
- `confidence` is recorded for review only. It must not trigger routing by itself.

## 5. Route Decision Object

Python routing should produce one `RouteDecision` object before any side effect.

```python
RouteDecision(
    route="forwarded_keep_open",
    category="education",
    sub_type="rejected",
    action="front_forward_to_sybil",
    customer_action="draft_ack",
    internal_target="sybil@dify.ai",
    inbox_target=None,
    close_conversation=False,
    state_step="forwarded_keep_open",
    reason="Eligible education review requires Sybil handoff",
)
```

Required decision fields:

| Field | Meaning |
|---|---|
| `route` | Stable route name used in logs/tests |
| `category` / `sub_type` | Normalized classifier category |
| `action` | Tool action or `skill_flow` |
| `customer_action` | `none`, `draft`, `draft_ack`, `direct_reply`, or `skill_policy` |
| `internal_target` | Internal email target when applicable |
| `inbox_target` | Front inbox target when applicable |
| `close_conversation` | Whether automation may close/archive |
| `state_step` | State saved after the action |
| `reason` | Short human-readable route reason |

## 6. Routing Decision Table

| Category / Case | Required Evidence | Route | System Action | Customer Action | Target | State Step | Close? |
|---|---|---|---|---|---|---|---|
| spam / ads | Ads, sponsorship, SEO, backlinks, guest posts, promotion, unsolicited sales | `spam_auto_close` | `front_close_conversation` | none | none | `closed_spam` | yes |
| security | Vulnerability, disclosure, abuse, data leak, security incident | `security_move_inbox` | `front_forward_to_security` | none by default | inbox `Security` | `moved_inbox` | no |
| unclear | Route cannot be determined from rules | `manual_review_bobby` | `front_forward_to_bobby` | none by default | `bobby@dify.ai` | `manual_review` | no |
| partnership / marketplace | Marketplace/plugin/template/community ecosystem cooperation | `partnership_forwarded_keep_open` | `front_forward_to_community` or `front_forward_to_partnerships` | none by default | `marketing@dify.ai` | `forwarded_keep_open` | no |
| education eligible review | Higher education application/rejection with school info | `education_sybil_forwarded_keep_open` | create Linear when needed, then `front_forward_to_sybil` | draft acknowledgement | `sybil@dify.ai` | `forwarded_keep_open` | no |
| education not eligible | K-12, personal email only, or clearly not eligible | `education_draft_keep_open` | `front_create_draft` | draft rejection/info request | none | `draft_created` | no |
| account SaaS issue with Linear | Login, deletion/transfer/compromise for verified SaaS accounts | `account_sybil_forwarded_keep_open` | create Linear, then `front_forward_to_bobby` | draft acknowledgement when useful | `bobby@dify.ai` | `forwarded_keep_open` | no |
| account quota/plan anomaly | quota mismatch, plan changed unexpectedly | `account_anomaly_forwarded_keep_open` | create Linear, then `front_forward_to_sybil` with `cc_email=bobby@dify.ai` | draft acknowledgement when useful | `sybil@dify.ai`, CC `bobby@dify.ai` | `forwarded_keep_open` | no |
| billing | Refund, invoice, duplicate charge, downgrade | `billing_skill_flow` | skill decides draft/ticket | draft by default | skill policy | `skill_in_progress` or final state | no by default |
| legal | Legal threat, lawyer letter, lawsuit | `legal_forwarded_keep_open` | sent Front forward to `geyan@dify.ai` with original thread and summary | no automatic reply | Geyan | `forwarded_keep_open` | no |
| investment | Investor/VC/fundraising | `investment_forwarded_keep_open` | forward to Claudia if configured | none by default | Claudia, optional Bobby visibility | `forwarded_keep_open` | no |
| technical free | Technical support without paid/Premium evidence | `technical_template_or_draft` | technical skill | approved template or draft | none | skill policy | policy |
| technical paid/Premium | Paid/Premium technical issue | `technical_ticket_or_draft` | technical skill, Linear when needed | draft or ticket acknowledgement | CUS Linear | skill policy | no by default |

## 7. State Machine and Action Log

Use clear state steps so webhook reprocessing is predictable. `conversation_states.sender_email` stores the original customer sender once known and must not be overwritten by later internal forwards or teammate messages. Customer draft recipients should use this preserved sender, not the current Front conversation recipient.

| State Step | Meaning | Reprocessable? | Waiting User? | Auto Close? |
|---|---|---|---|---|
| `initial` | New or unprocessed conversation | yes | no | no |
| `classified` | Classification stored, no side effect yet | yes | no | no |
| `draft_created` | Customer draft created for human review | no | no | no |
| `forwarded_keep_open` | Internal Front handoff sent; conversation remains open | no | no | no |
| `moved_inbox` | Conversation moved to another Front inbox | no | no | no |
| `manual_review` | Bobby review required | no | no | no |
| `waiting_user` | Draft/reply asks user for more info | yes, when user replies | yes | stale-close policy only |
| `closed_spam` | Spam/ads archived by automation | no | no | already closed |
| `failed_needs_review` | Tool failed or route unsafe | no | no | no |
| `done` | Explicitly completed by policy | no | no | policy only |

Preferred non-spam handoff state is `forwarded_keep_open`.

`conversation_actions` provides tool-level idempotency for external write operations. Its uniqueness key is `conversation_id + action_type + action_key`. Record only successful side effects; failed actions may be retried. Current action keys:

| Tool | Action Key |
|---|---|
| `front_create_draft` | normalized draft body hash |
| `linear_create_ticket` | normalized title hash |
| `feishu_notify_sybil_group` / `front_forward_to_sybil` | handoff type + Linear URL, or message hash when no URL exists |
| `front_forward_to_bobby` / `front_forward_to_limin` / other internal forwards | summary/message hash |

This is not conversation-level blocking. If the user provides new information and the system generates materially different action content, the new action can still execute.

## 8. Customer Reply Policy

| Situation | Customer-Facing Behavior |
|---|---|
| Spam / ads | No reply |
| Security | No automatic customer reply by default |
| Legal | No automatic customer reply by default |
| Unclear | No automatic customer reply by default |
| Marketplace / partnership | No automatic customer reply by default |
| Education eligible review | Draft acknowledgement, not direct send |
| Education not eligible | Draft explanation, not direct send |
| Account paid/login/ops | Draft acknowledgement when helpful, then handoff to Bobby (quota/plan anomaly -> Sybil) |
| Billing/refund/invoice | Draft by default unless policy explicitly permits otherwise |
| Technical free | Approved template may direct-send only if skill allows |
| Technical paid/Premium | Draft/ticket according to skill |

Default: if unsure, draft or no reply. Do not direct-send.

## 9. Internal Handoff Contract

All internal handoffs must use Front forwarding and include:

- conversation ID
- original sender email
- summary
- route reason
- category/sub_type
- Linear URL if created
- original Front conversation content

Hard restrictions:

- Handoff tools cannot use `sender_email` as `to_email`.
- Handoff tools can only send to configured internal recipients.
- Handoff tools do not close conversations.
- Handoff tools do not create customer replies.

Current recipients:

| Path | Recipient / Target |
|---|---|
| Bobby review | `bobby@dify.ai` |
| Account quota/plan anomaly with Linear | `sybil@dify.ai`, CC `bobby@dify.ai` (for anomaly only) |
| Education review | `sybil@dify.ai` |
| Marketplace/community/plugin ecosystem | `marketing@dify.ai` |
| Security | Front inbox `Security` |

## 10. Failure Handling

| Failure | Required Handling |
|---|---|
| Classification JSON parse fails | Treat as `unclear`, route to Bobby, keep open |
| Route has missing required evidence | Route to Bobby, keep open |
| Front forward fails | Add internal comment if possible, set `failed_needs_review`, keep open |
| Front close spam fails | Set `failed_needs_review`, keep open |
| Security inbox not found | Route to Bobby instead of dropping conversation |
| Linear ticket creation fails | Do not proceed as successful handoff; route to Bobby with failure summary |
| Attachment parsing fails | Continue with conversation text, record attachment failure in summary/state |
| Duplicate webhook event | Idempotency skip via `webhook_events` |
| Duplicate tool side effect | Return prior successful result from `conversation_actions` |
| Handler exception | Notify Bobby, explicitly reopen the original conversation, save `failed_needs_review` |
| Tool returns unknown result | Set `failed_needs_review` |

## 11. Test Strategy

### Unit Tests

- classification JSON parser accepts raw JSON, fenced JSON, and JSON with surrounding text
- invalid category normalizes to `unclear`
- no fixed confidence threshold changes route
- spam route closes
- security route moves to `Security`
- partnership routes to `marketing@dify.ai`
- unclear routes to Bobby
- handoff tools reject empty conversation_id or empty recipient
- action log guards exist for duplicate-prone write tools
- Front draft creation uses preserved original sender, not internal handoff recipient

### Route Table Tests

Each routing table row gets at least one test fixture with expected:

- route
- tool/action
- customer_action
- state_step
- target
- close/open

### Tool Safety Tests

- `tools/handoff.py` never forwards to sender/customer address
- forward body includes original Front thread text
- non-spam handoffs do not call `front_close_conversation`

### Historical Replay

Use `docs/support-inbox-test-set-50.md` after rules are accepted. For each conversation record:

- expected route
- predicted category
- selected route
- customer action
- internal target or inbox target
- close/open decision
- pass/fail
- correction note

## 12. Implementation Phases

1. Finalize this spec.
2. Implement classification parser and route decision objects.
3. Implement Front handoff tools and remove active Feishu runtime code.
4. Refactor orchestrator to call deterministic routing before skill flow.
5. Update skills to new tool names and explicit reply policies.
6. Add route table and tool safety tests.
7. Run compile, unit tests, and grep safety checks.
8. Replay 50 historical Support conversations.
9. Review results with user.
10. Deploy only after explicit approval.

## 13. Deployment And Rollback

Deployment is manual and requires approval.

Before deployment:

```bash
python -m compileall main.py tools config.py agent webhooks routes
python tests/test_routing.py
rg -n "open\.feishu\.cn|webhook/feishu|feishu_card|FEISHU_|SMTP_|NOTIFICATION_EMAIL|email_notify" main.py tools config.py agent webhooks routes skills README.md .env.example
```

Rollback plan:

- Keep current production screen unchanged until cutover.
- Keep previous commit hash before deployment.
- If the new service misroutes, stop new service and restart from previous commit/env.
- Because non-spam handoffs stay open, incorrect handoffs remain visible for manual correction.

## 14. Definition Of Stable

The system is stable only when:

- active code has no Feishu runtime path
- active code has no SMTP notification path
- no fixed confidence threshold controls routing
- spam/ads auto-close is isolated to clear spam/ads
- security moves to `Security`
- Marketplace/community/plugin cooperation goes to `marketing@dify.ai`
- education eligible review goes only to Sybil
- account login/ops Linear handoff goes to Bobby; account quota/plan anomaly goes to Sybil with Bobby CC
- all internal handoffs preserve original Front content
- non-spam handoffs use `forwarded_keep_open`
- deterministic tests pass
- 50-history replay is reviewed
- user explicitly approves deployment
