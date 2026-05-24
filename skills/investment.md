# Skill: Investment / Fundraising / Investor Relations

## Purpose
Handle investment inquiries, fundraising, VC relationships, and investor relations requests. Forward to Claudia Liu (刘景媛) at claudia@dify.ai.

## Steps

### 1. Analyze the inquiry
Determine if this is:
- **fundraising**: Dify is raising funds, investor due diligence, term sheet questions
- **investor_relations**: Existing investors, portfolio updates, board matters
- **partnership_investment**: Strategic investment, joint venture, M&A discussions
- **media_press**: Press inquiries about funding or investment

### 2. Forward to Claudia
- Call `front_forward_to_investment` — creates a forward draft to Claudia Liu (claudia@dify.ai) for Bobby to review and send

**Important**: Do NOT call `front_create_draft` to reply to the user. Only create the forward draft.

### 3. Bobby's Workflow
1. AI creates forward draft (no action needed from you yet)
2. You review and send the draft manually in Front
3. No automatic reply sent to the user — you decide what to tell them after sending

## Routing

| Type | To | CC |
|------|----|----|
| All investment inquiries | Claudia Liu (claudia@dify.ai) | — |