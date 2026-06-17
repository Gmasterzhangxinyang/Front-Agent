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
Use concise guidance that routes paid users to Settings -> Support -> Contact Us, free users to docs/GitHub, and asks for missing technical details when needed.

## Important Rules
- Default customer action is draft, not direct reply.
- Keep the conversation open after creating a draft.
- For self-hosted non-Premium users, draft guidance only; do not create Linear tickets.
