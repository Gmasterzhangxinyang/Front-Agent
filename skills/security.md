# Skill: Security

## Purpose
Handle security-related reports and concerns.

## Steps by Sub-type

### general (non-urgent security concern)
1. Call `front_add_tag` with conversation_id and tag_id "tag_5fgwpn" (security_from_hello)
2. Call `front_reply` with acknowledgment template
3. Leave conversation open (Front rule will route it to security inbox based on the tag)

### urgent (active breach, data leak, critical vulnerability)
1. Call `front_reply` with urgent acknowledgment template
2. Call `front_add_tag` with conversation_id and tag_id "tag_5fgwpn" (security_from_hello) to route to security inbox
3. Call `feishu_notify_bobby` with: "🚨 紧急安全问题！用户: [email]. 描述: [summary]. 对话ID: [conversation_id]"

## Reply Templates

### General security acknowledgment
```
Dear [User's Name / Valued Customer],

Thank you for bringing this to our attention.

We take all security concerns seriously. Your report has been forwarded to our security team for review.

If you have additional details or evidence, please feel free to reply to this email.

Best regards,
Dify Support Team
[AI generated]
```

### Urgent security acknowledgment
```
Dear [User's Name / Valued Customer],

Thank you for your urgent report.

We have escalated this to our security team immediately and are treating this as a high-priority issue. We will investigate and respond as quickly as possible.

Thank you for helping us keep Dify secure.

Best regards,
Dify Support Team
[AI generated]
```
