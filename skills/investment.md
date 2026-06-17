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
- Call `front_forward_to_investment` — forwards directly to Claudia Liu (claudia@dify.ai)

### 3. Notify Bobby
- Call `front_forward_to_bobby` with conversation_id and message: "📬 投资类邮件已转发\n发件人: [sender_email]\n对话ID: [conversation_id]\n类型: investment\n\n已通过 Front forward 转发至 Claudia Liu (claudia@dify.ai)"

### 4. Keep open after handoff
- Call `state_set` with step="forwarded_keep_open" so Bobby can verify routing

**Important**: Do NOT call `front_create_draft` to reply to the user. Only forward to Claudia.

### 3. Bobby's Workflow
1. AI forwards directly to Claudia and forwards the Front thread summary to Bobby
2. No automatic reply sent to the user

## Routing

| Type | To | CC |
|------|----|----|
| All investment inquiries | Claudia Liu (claudia@dify.ai) | — |