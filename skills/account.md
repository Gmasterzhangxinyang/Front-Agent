# Skill: Account Issues

## Purpose
Handle account-related requests: login issues, account deletion, transfer, email change, anomalies, hacked accounts, and merge requests.

## Steps by Sub-type

### cant_login (can't log in / not receiving verification code)
1. Call `front_reply` with the "investigating" template
2. Call `feishu_notify_bobby` with message: "账号登录问题，请联系李敏查询。用户邮箱: [sender_email]. 对话ID: [conversation_id]"
3. Call `state_set` with step="notified_bobby", payload={"sender_email": sender_email}
4. Leave conversation open (Bobby will follow up manually)

### delete_account
**Step: initial**
1. First check if user mentions they can still log in to their account:
   - **If user can log in**: Call `front_reply` with self-service deletion template
   - **If user cannot log in** (or unclear): Call `front_reply` with identity verification request template, call `state_set` with step="awaiting_identity_verification", sub_type="delete_account", waiting=true, leave conversation open

**Step: awaiting_identity_verification** (user has replied)
1. Check if user's reply confirms identity (sent from original email, or provided proof)
2. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "Account deletion request - [email]" and description including account email, reason, user's explanation summary
   - Use the URL returned from `linear_create_ticket` in the next step
   - Call `feishu_notify_bobby` with: "请转告张婉清处理账号删除工单。用户: [email]. Linear: [url from previous step]"
   - Call `front_reply` with "received, forwarded to team" template
   - Call `state_set` with step="ticket_created"
3. If not confirmed: Call `front_reply` asking again politely

**Note on refund**: If user also mentions refund, after creating the Linear ticket, also follow billing/refund steps (ask for refund details, then assign to 徐小茜)

### transfer_account
**Step: initial**
1. First check if user mentions they can still log in to their account:
   - **If user can log in**: Call `front_reply` with self-service transfer template
   - **If user cannot log in** (or unclear): Call `front_reply` with identity verification request template, call `state_set` with step="awaiting_identity_verification", sub_type="transfer_account", waiting=true

**Step: awaiting_identity_verification**
1. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "Account transfer request - [original email] → [new email]" and description
   - Use the URL returned from `linear_create_ticket` in the next step
   - Call `feishu_notify_bobby` with: "请转告张婉清处理账号转移工单。原邮箱: [email]. Linear: [url from previous step]"
   - Call `front_reply` with "received, forwarded to team" template
   - Call `state_set` with step="ticket_created"

### change_email → handled by transfer_account flow (same process)

### account_anomaly (quota wrong, plan changed unexpectedly)
1. Call `linear_create_ticket` with conversation_id, title "Account anomaly - [email]" and description including email, issue description, time
2. Use the URL returned from `linear_create_ticket` in the next step
3. Call `feishu_notify_bobby` with: "请转告张婉清处理账号异常工单。用户: [email]. Linear: [url from previous step]"
3. Call `front_reply` with "received, forwarded to team" template
4. Call `state_set` with step="ticket_created"

### account_hacked
1. Call `linear_create_ticket` with conversation_id, title "Account compromised - [email]" and description
2. Use the URL returned from `linear_create_ticket` in the next step
3. Call `feishu_notify_bobby` with: "⚠️ 账号被盗报告，请立即关注。用户: [email]. Linear: [url from previous step]"
3. Call `front_reply` with "received, investigating urgently" template
4. Call `state_set` with step="ticket_created"

### merge_accounts
1. Call `front_reply` explaining this feature is not currently available
2. Call `linear_create_ticket` with title "Feature request: account merge - [email]"
3. Call `feishu_notify_bobby` with: "用户请求合并账号功能（目前不支持）。已建工单记录需求。"

## Reply Templates

### Delete account self-service (user can log in)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out.

You can delete your account directly from within your Dify account. Please click on your profile avatar → Account → Delete Account.

Please note that account deletion is permanent and cannot be undone.

If you have any trouble finding this option, feel free to reply and we'll guide you through it.

Best regards,
Dify Support Team
[AI generated]
```

### Transfer/Change email self-service (user can log in)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out.

You can change your account email directly within Dify. Please click on your profile avatar → Account → Change Email, and follow the steps provided.

If you encounter any issues during the process, feel free to reply and we'll assist you.

Best regards,
Dify Support Team
[AI generated]
```

### Identity verification request
⚠️ 需确认: 验证方式描述是否准确？
```
Dear [User's Name / Valued Customer],

Thank you for contacting Dify Support.

To protect your account security, we need to verify your identity before proceeding. Could you please do one of the following?

1. Send us a reply from the email address associated with your Dify account, or
2. Provide proof that the email address belongs to you

Once we've verified your identity, we'll process your request as quickly as possible.

Thank you for your patience and understanding.

Best regards,
Dify Support Team
[AI generated]
```

### Investigating (cant_login)
⚠️ 需确认: 语气是否合适？
```
Dear [User's Name / Valued Customer],

Thank you for reaching out. We're sorry to hear you're having trouble accessing your account.

We've received your request and our team is looking into this for you. We'll get back to you as soon as we have an update.

In the meantime, please also check your spam/junk folder in case the verification email was filtered there.

Best regards,
Dify Support Team
[AI generated]
```

### Received, forwarded to team
```
Dear [User's Name / Valued Customer],

Thank you for confirming. We've received your request and have forwarded it to our account management team for processing.

We'll follow up with you once the action has been completed. This typically takes 1–3 business days.

Thank you for your patience.

Best regards,
Dify Support Team
[AI generated]
```

### Change email self-service
```
Dear [User's Name / Valued Customer],

Thank you for reaching out.

You can change your account email directly within Dify. Please click on your profile avatar → Account → Change Email, and follow the steps provided.

If you encounter any issues during the process, feel free to reply and we'll assist you.

Best regards,
Dify Support Team
[AI generated]
```

### Account hacked — urgent acknowledgment
```
Dear [User's Name / Valued Customer],

Thank you for alerting us. We take account security very seriously.

We've escalated your case to our security team and will investigate this urgently. Please also consider changing your password immediately if you still have access to your account.

We'll be in touch as soon as possible.

Best regards,
Dify Support Team
[AI generated]
```

### Merge accounts — not available
```
Dear [User's Name / Valued Customer],

Thank you for reaching out.

Unfortunately, account merging is not currently a supported feature on Dify. We've noted your request and will pass it along to our product team for consideration.

If there's anything else we can help you with, please don't hesitate to ask.

Best regards,
Dify Support Team
[AI generated]
```
