# Skill: Technical Support

## Purpose
Handle technical issues: workflow problems, bug reports, how-to questions, feasibility inquiries, API issues, outages, data privacy, and self-hosted configuration.

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

### 2. Create a draft by default
- Call `front_create_draft` with the approved technical support guidance.
- Do NOT call `front_reply_with_template` unless Bobby has explicitly approved direct-send for this exact case.
- Do NOT close the conversation automatically.
- Call `state_set` with step="draft_created".

## Draft Guidance
Create a concise Front draft based on the user's support eligibility. Do not send it directly.

### Paid users
Use this path only when the email clearly shows `Current Plan: professional`, `Current Plan: team`, or `Current Plan: premium`, or the user explicitly says they are on a paid Dify plan.

- Guide the user to submit a support ticket from Dify: Settings -> Support -> Contact Us.
- Ask them to include workspace ID, app ID, workflow link, exact error message, screenshots, and reproduction steps.
- If the issue is urgent or service-blocking, acknowledge the urgency in the draft, but still keep it as a draft for Bobby to review.

### Non-paid users
Use this path when the user is on Sandbox/free, self-hosted open-source/Community Edition, or when there is no clear paid-plan evidence.

- Guide them to the Dify community, docs, and GitHub issues for technical support.
- For reproducible bugs, ask them to open a GitHub issue with version, deployment type, logs, screenshots, and reproduction steps.
- Do not create Linear tickets for non-paid technical support.
- Do not imply dedicated engineering support for free or community users.

### Missing details
If the email lacks enough technical detail, ask for the missing facts in the draft and choose the paid or non-paid support path above based on plan evidence.

## Important Rules
- Default customer action is draft, not direct reply.
- Keep the conversation open after creating a draft.
- If there is no explicit paid-plan evidence, treat the technical request as non-paid and guide to community/GitHub.
- For self-hosted non-Premium users, draft guidance only; do not create Linear tickets.
