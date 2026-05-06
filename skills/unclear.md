# Skill: Unclear / Unclassified

## Purpose
Handle emails that cannot be confidently classified into any other category.

## Steps
1. Call `front_create_draft` with generic acknowledgment template
2. Call `feishu_notify_bobby` with: "邮件分类不确定，请人工判断。发件人: [sender_email]. 摘要: [summary]. 对话ID: [conversation_id]"
3. Leave conversation open

## Reply Template

```
Dear [User's Name / Valued Customer],

Thank you for reaching out to Dify Support.

We've received your email and our team will review it shortly. We'll get back to you as soon as possible.

Thank you for your patience!

Best regards,
Dify Support Team
[AI generated]
```
