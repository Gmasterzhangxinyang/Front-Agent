# Skill: Unclear / Manual Review

## Purpose
Handle emails that cannot be safely classified or routed by the existing rules.

## Steps
1. Do NOT send a customer reply and do NOT create a customer draft by default.
2. Call `front_forward_to_bobby` with conversation_id and message: "邮件分类不确定，请人工判断。发件人: [sender_email]. 摘要: [summary]. 对话ID: [conversation_id]"
3. Call `state_set` with step="manual_review", waiting=false.
4. Leave conversation open.

## Important
- This is a manual review path, not a customer response path.
- Bobby decides whether a customer draft/reply is needed.
