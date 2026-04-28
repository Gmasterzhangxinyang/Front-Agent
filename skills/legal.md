# Skill: Legal Threats

## Purpose
Handle emails containing legal threats, lawyer letters, or lawsuit mentions.

## Steps
1. Call `front_reply` with acknowledgment template (calm, professional, non-committal)
2. Call `feishu_notify_bobby` with: "⚠️ 法律威胁邮件！请立即处理。发件人: [sender_email]. 摘要: [summary]"
3. Leave conversation open (Bobby will handle manually)

## Reply Template

### Legal threat acknowledgment
⚠️ 重要: 此模板措辞需谨慎，请Bobby确认后再使用
```
Dear [User's Name / Valued Customer],

Thank you for your email.

We have received your message and have forwarded it to the appropriate team for review. We take all communications seriously and will respond in due course.

Best regards,
Dify Support Team
```
