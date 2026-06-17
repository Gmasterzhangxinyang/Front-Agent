# Stable Agent V2 Plan

This plan combines the earlier architecture optimization plan with the updated colleague handoff decision: no Feishu workflow, no SMTP notification sender, and internal handoffs through Front forwarding.

## 1. Operating Principle

- Keep the currently running production service unchanged until the new version is reviewed and intentionally deployed.
- All optimization work happens on `refactor/stable-agent-v2`.
- Do not restart, kill, or replace the running `screen` service during refactor work.
- Treat the current branch as a new version, not a live hotfix.

## 2. Target Outcome

Build a stable support automation system that can:

1. Classify incoming Front conversations reliably.
2. Select the correct business route with explicit confidence thresholds.
3. Draft customer-facing replies in Front unless a rule explicitly allows direct send.
4. Create Linear tickets with enough original context.
5. Forward internal handoffs through Front to the right colleague or team.
6. Preserve original customer email content in every handoff.
7. Avoid hidden side effects such as notifying customers from internal handoff code.

## 3. Major Architecture Problems To Fix

| Area | Current Problem | Target Direction |
|---|---|---|
| Classification | One-shot category decisions can be inaccurate, especially mixed intent emails. | Use stricter schema, confidence gates, evidence fields, and fallback review paths. |
| Skills | Skill files mix routing, reply policy, escalation policy, and templates. | Split each skill into decision rules, tool actions, and response templates. |
| Tool naming | Legacy `feishu_notify_*` names no longer describe behavior. | Keep wrappers temporarily, then rename to Front-forward tools after skills are stable. |
| Human handoff | Previous Feishu card workflow introduced callback state, duplicate callbacks, and button semantics. | Remove interactive callback workflow. Use Front forward only. |
| Internal recipients | Routing has been person-specific and scattered across skills/config. | Centralize recipients in config and document ownership clearly. |
| Forwarding original content | Some forwarding paths were fragile or summary-only. | Every handoff must include summary plus original Front conversation content. |
| Customer safety | Internal notification code must never email customers. | Only Front reply/draft tools communicate with customers. Handoff tools only send to configured internal recipients. |
| Observability | Tool failures can be hard to diagnose. | Add clearer return values, comments, and eventually structured logs/metrics. |
| Testing | Existing checks are mostly manual. | Add focused tests for classification contract, forwarding body construction, and tool routing. |

## 4. Notification And Handoff Decision

### Final Decision

Use Front forwarding for internal colleague handoffs.

Do not use:

- Feishu cards
- Feishu webhooks
- Feishu button states such as `已解决` / `已转告`
- SMTP notification sender
- `NOTIFICATION_EMAIL_FROM`
- direct notification emails generated outside Front

### Required Behavior

For education/account/manual review handoffs:

1. The agent summarizes the case.
2. If a Linear ticket was created, the summary includes the Linear URL.
3. The agent forwards the Front conversation to the colleague through Front.
4. The forwarded body includes the original Front conversation content.
5. The customer is not sent anything by the handoff tool.
6. Customer-facing replies remain Front drafts or Front replies handled by existing Front tools.

For security reports, the target behavior is different: move the conversation to the Security inbox, not forwarding to a named person.

### Config

Internal handoff recipients are configured with:

```env
INTERNAL_FORWARD_BOBBY_EMAIL=bobby@dify.ai
INTERNAL_FORWARD_LIMIN_EMAIL=bobby@dify.ai
INTERNAL_FORWARD_SYBIL_EMAIL=sybil@dify.ai
```

### Temporary Compatibility

Keep the legacy tool names temporarily:

- `feishu_notify_bobby`
- `feishu_notify_limin`
- `feishu_notify_sybil`

These now mean “Front-forward the original conversation to the configured colleague.” The 李敏 compatibility path currently forwards to Bobby. They do not call Feishu.

After the new version is stable, rename them to clearer names:

- `front_forward_to_bobby`
- `front_forward_to_limin`
- `front_forward_to_sybil`

## 5. Routing Rules To Stabilize

| Category / Case | Target Handling |
|---|---|
| Marketplace / community / plugin / ecosystem cooperation | Forward original Front thread to `marketing@dify.ai`. |
| Education plan review | Create Linear when needed, then Front-forward summary + Linear URL + original thread to `sybil@dify.ai`. |
| Account verification / blacklist / paid login issue | Draft customer acknowledgement, then Front-forward summary + original thread to Bobby for now. |
| Security emergency | Move the Front conversation from Support/Hello inbox to the Security inbox. Do not separately forward to Yongle in V2. |
| Investment / IR | Forward to Claudia, then Front-forward summary to Bobby if visibility is needed. |
| Legal threat | Do not auto-send customer reply unless safe; Front-forward summary + original thread to Bobby/legal path. |
| Unclear classification | Draft generic acknowledgement only when appropriate, then Front-forward to Bobby for manual judgment. |

## 6. Refactor Phases

| Phase | Goal | Work Items | Done Criteria |
|---|---|---|---|
| 0. Production Safety | Keep current running code unchanged. | Work only on branch; do not restart screen; keep commits small. | Running service still untouched. |
| 1. Remove Feishu Runtime | Delete Feishu callback/API behavior. | Remove Feishu callback route, card builders, tenant token calls, button-state workflow. | No `open.feishu.cn`, `FEISHU_*`, `webhook/feishu`, or card callback references in active code. |
| 2. Front Forward Handoff | Replace internal notifications with Front forwards. | Use `front.forward_conversation_direct`; require `conversation_id`; include summary/Linear/original thread. | No SMTP notification config/helper; handoff tools send only to internal configured recipients. |
| 3. Skill Cleanup | Make business routing explicit. | Update education/account/security/unclear/investment skills to pass `conversation_id` and concise summary. | Tool calls are deterministic and include required fields. |
| 4. Classification Hardening | Improve intent detection. | Add evidence fields, confidence thresholds, mixed-intent handling, and “manual review” criteria. | Classification JSON is strict and repeatable; low confidence falls back safely. |
| 5. Tool Naming Cleanup | Remove misleading legacy names. | Rename `feishu_notify_*` to `front_forward_to_*`; update skills and registry together. | No Feishu names remain except historical docs/record files. |
| 6. Test Coverage | Prevent regressions. | Add tests for forward body, routing recipients, no-customer handoff, classification schema. | Tests run locally before merge/deploy. |
| 7. Deployment Review | Decide when to replace current service. | Review diffs, env vars, logs, and rollback plan. | User explicitly approves deploy/restart. |

## 7. Validation Checklist

Before any deployment:

```bash
python -m compileall main.py tools config.py agent webhooks routes
rg -n "open\.feishu\.cn|webhook/feishu|feishu_card|FEISHU_|notification_channel|SMTP_|NOTIFICATION_EMAIL|email_notify" main.py tools config.py agent webhooks routes README.md .env.example skills
rg -n "sender_email.*internal_forward|send_email\(|notification_email" tools agent config.py skills
```

Expected results:

- Compile succeeds.
- No active Feishu API/callback references.
- No SMTP notification helper/config references.
- Internal handoff recipients come only from `INTERNAL_FORWARD_*` config.
- Customer sender email is never used as an internal handoff recipient.

## 8. Current Branch Status

Current branch: `refactor/stable-agent-v2`

Relevant commits:

- `1c6fcca refactor: switch notifications to email only`
- `bc0770e refactor: forward colleague handoffs through Front`

The second commit corrects the handoff model: internal colleague handoffs go through Front forwarding, not SMTP.

## 9. Open Questions Before Final Architecture Cleanup

1. `INTERNAL_FORWARD_BOBBY_EMAIL`: `bobby@dify.ai`
2. `INTERNAL_FORWARD_LIMIN_EMAIL`: `bobby@dify.ai` for now; account/blacklist handoffs route to Bobby.
3. Should education go directly to `sybil@dify.ai` only, or also CC another education owner?
4. Should Front forwards be sent immediately, or created as shared drafts for Bobby review in some categories?
5. Which categories are allowed to auto-close after handoff?
