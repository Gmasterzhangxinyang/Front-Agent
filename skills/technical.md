# Skill: Technical Support

## Purpose
Handle technical issues: workflow problems, bug reports, how-to questions, feasibility inquiries, API issues, outages, data privacy, and self-hosted configuration.


## Draft Quality Bar
- Start with a complete, authoritative English version; never create a local-language-only customer draft.
- If the latest customer message is primarily non-English, finish the English version first, then write exactly `For reference, a <Language> translation is provided below.` and add a faithful matching-language version.
- Front automatically appends the configured default signature. Do not put `Best regards,`, `Dify Support Team`, `Cheers`, a personal name, or any other manual sign-off in the draft body; keep every language block unsigned.
- If the customer wrote in English, do not add a second language version.
- For approved deterministic templates marked verbatim, preserve the English body exactly; for a non-English customer, append only the required reference notice and a faithful matching-language translation.
- Answer only what the email supports. Do not invent product behavior, policy exceptions, timelines, refunds, eligibility, or engineering commitments.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an issue is fixed, approved, refunded, or escalated unless a tool result or policy explicitly proves it.
- Do not open a reply by emphasizing that the customer is on a free, Sandbox, unknown, or Community plan. First acknowledge and briefly restate the specific problem; mention plan-based support boundaries later, only when they affect the next step.
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps

### 1. Analyze the technical issue
Determine the sub_type:
- **workflow_issue**: Workflow not working, step failing
- **bug_report**: Something broken, unexpected behavior
- **how_to**: How to do X, how to configure Y
- **feasibility**: Can Dify do X? Evaluating before purchase
- **api_issue**: API limits, API key, API usage
- **outage**: Service down, can't access Dify at all
- **data_privacy**: Questions about data storage, training, GDPR
- **self_hosted**: Self-hosted installation/config (non-Premium)


### 2. Route support; do not solve the technical issue directly
- Do not provide step-by-step technical fixes, configuration values, code snippets, or claims about whether a setting is supported unless Bobby explicitly asks for a direct technical answer.
- For technical how-to, configuration, API, feature behavior, privacy, and self-hosted questions, use `docs_search` only to choose 1-3 relevant recommended links for the user to review. Do not turn search results into a direct solution.
- For reproducible bugs, errors, stack traces, regressions, or self-hosted failures, use `github_search` only to find the most relevant GitHub issues/discussions link or confirm that GitHub issue submission is the right next step.
- If no useful link is found, still route the user by support eligibility and ask them to include deployment type, version, exact error, logs/screenshots, and reproduction steps in the correct channel.

### 3. Linear ticket policy
- Do not create Linear tickets for non-paid technical support, self-hosted Community Edition, or unclear paid-plan evidence.
- Create `linear_create_ticket` only when there is clear paid/Premium/SaaS support evidence AND the issue is reproducible, urgent, service-blocking, or likely a Dify product bug.
- Linear is strictly internal. Never include a Linear issue URL, ID, title, or mention of an internal tracking ticket in a customer-facing draft.
- If you create a Linear ticket, keep its result in internal tools/comments only, then create the customer-facing Front draft without any Linear reference and call `state_set` with step="draft_created".
- If Linear creation fails, do not pretend it succeeded. Create a draft asking for missing details or route for manual review by state if needed.

### 4. Create a draft by default
- Call `front_create_draft` with the approved technical support guidance and any relevant recommended links.
- Do NOT call `front_reply_with_template` unless Bobby has explicitly approved direct-send for this exact case.
- Do NOT close the conversation automatically.
- Call `state_set` with step="draft_created".

## Draft Guidance
Create a concise Front draft based on the user's support eligibility. Do not send it directly. Slightly adapt the template to the user's issue, but do not directly answer how to implement or configure the technical solution.

### Paid users
Use this path only when the email clearly shows `Current Plan: professional`, `Current Plan: team`, or `Current Plan: premium`, or the user explicitly says they are on a paid Dify plan.

- Politely frame the support route as a paid-plan benefit: tell Pro and Team subscribers that they have access to priority technical support.
- Gently ask them to submit a support ticket by clicking the question mark icon next to the personal avatar in the Dify dashboard, then selecting Contact Us, so the priority support team can receive and investigate the case through the correct channel.
- Ask them not to remove subscription verification details from the submitted ticket, because those details are required to confirm account status.
- Keep this initial routing draft concise. Do not enumerate what the ticket should contain and do not add a checklist of workspace IDs, app IDs, run IDs, logs, screenshots, providers, timestamps, or reproduction steps.
- If the issue is urgent or service-blocking, acknowledge the urgency in the draft, but still keep it as a draft for Bobby to review.

### Premium custom multi-AZ / Active-Active architecture
Use this approved guidance only when a Premium customer explicitly proposes a dual-AZ or multi-AZ Active-Active deployment, typically behind a load balancer and with shared services such as S3, RDS/PostgreSQL, or ElastiCache/Redis, to meet high-performance or high-availability requirements.

- Add a paragraph explaining that this custom topology differs from the current standard one-click Premium deployment on AWS Marketplace. Dify cannot predict the engineering complexity or issues that may arise during implementation, so this deployment approach is not recommended.
- This is an approved exception to the general rule against direct technical conclusions. Do not provide environment-variable values, implementation steps, architecture validation, or any additional claim about licensing or support coverage.
- Then recommend Dify Enterprise for the production requirements described by the customer.
- For a clearly Japanese customer, ask whether they consent to having the inquiry shared with and being connected to the Japan sales team. Do not claim it has already been forwarded, and do not replace the consent question with the generic `business@dify.ai` instruction.

Use this Japanese paragraph only in the Japanese reference version after the complete English version and required reference notice:

```
高性能・高可用性要件に対応するため、Dify Premiumを2つのAZにまたがるActive-Active構成でデプロイすることをご検討とのことですが、この構成は、現在AWS Marketplaceで提供しているPremiumの標準的なワンクリックデプロイ構成とは異なります。そのため、具体的な導入時の技術的な難易度や発生し得る問題を事前に予測できず、この構成での運用は推奨しておりません。
```

Use this Chinese paragraph only in the Chinese reference version after the complete English version and required reference notice:

```
您提到希望通过双 AZ Active-Active 架构部署 Dify Premium，以满足高性能或高可用性需求。由于该部署架构与当前 Premium 版本在 AWS Marketplace 上的标准一键部署配置不同，我们无法预估具体实施中的工程难度及可能出现的问题，因此不建议采用该部署方式。
```

### Non-paid or unknown-plan users
Use this path when the user is on Sandbox/free, self-hosted open-source/Community Edition, or when there is no clear paid-plan evidence.

- Use this order: acknowledge the user's effort and specific symptom -> give a cautious, evidence-based explanation if one is available -> explain the applicable support channel without leading with plan limitations -> provide the concrete next step.
- The first substantive sentence must be about the user's issue, not their plan. Do not begin with wording such as "As a free-tier user", "Because you are on the free plan", or "Free users are not eligible".
- When the cause is not verified, say that it cannot yet be confirmed or that it may relate to a specific mechanism. Do not present an unverified mechanism as what "usually" happens.
- Recommend docs at https://docs.dify.ai and GitHub issues at https://github.com/langgenius/dify/issues for technical support.
- For reproducible bugs, ask them to open a GitHub issue with deployment type, version, logs/screenshots, exact error text, and reproduction steps.
- Do not create Linear tickets for non-paid technical support.
- Do not imply dedicated engineering support for free, unknown-plan, or community users.

### Commercial collaboration or licensing
If the technical question includes commercial collaboration, licensing, OEM/resale, or enterprise usage intent, include this guidance in the same draft:
- Ask them to email business@dify.ai with company name, company size, and specific use case.
- Ask them to use a corporate email address for verification.
- State that Dify can be used without additional commercial licensing when following Dify's open source license terms and not creating products that directly compete with Dify's services. Mention that Powered by Dify attribution is appreciated but not required.

### Missing details
If a paid user's email lacks technical detail, route them to priority support without asking them to repeat an exhaustive list of details in the email. For non-paid or unknown-plan users, ask only for the minimum missing facts needed for the docs/GitHub route.

## Important Rules
- Default customer action is draft, not direct reply.
- Keep the conversation open after creating a draft.
- If there is no explicit paid-plan evidence, treat the technical request as non-paid or unknown-plan and guide to docs/GitHub.
- For self-hosted non-Premium users, draft guidance only; do not create Linear tickets.
- Never expose internal ticketing links or internal issue metadata to customers.
- Keep any direct technical explanation minimal; the main answer should be the correct support channel and relevant links.
