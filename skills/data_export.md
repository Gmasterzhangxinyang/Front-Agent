# Skill: Data Export Request

## Purpose
Handle requests from users who want to export or download their personal data.

## Steps
1. Check if Dify has a self-service data export feature (currently: NO self-service export available)
2. If user's request is non-urgent:
   - Call `front_create_draft` with "no self-service export" template
3. If user's request is urgent (mentions legal reasons, GDPR, account deletion + data):
   - Call `front_create_draft` with "escalating" template
   - Call `feishu_notify_bobby` with: "用户请求数据导出（紧急）。发件人: [email]. 摘要: [summary]"
   - Leave conversation open

## Reply Templates

### No self-service export
⚠️ 需确认: 是否有其他数据导出方式？
```
Dear [User's Name / Valued Customer],

Thank you for reaching out.

At this time, Dify does not offer a self-service data export feature. We apologize for any inconvenience this may cause.

If you have an urgent need for your data (for example, for legal or compliance reasons), please reply with more details and we'll do our best to assist you.

Best regards,
Dify Support Team
[AI generated]
```

### Escalating urgent data export
```
Dear [User's Name / Valued Customer],

Thank you for your message.

We've received your data export request and have escalated it to our team for review. We'll follow up with you as soon as possible.

Best regards,
Dify Support Team
[AI generated]
```
