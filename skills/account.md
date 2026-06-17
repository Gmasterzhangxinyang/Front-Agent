# Skill: Account Issues


## Purpose
Handle account-related requests: login issues, account deletion, transfer, email change, anomalies, hacked accounts, and merge requests.

## SaaS vs Self-hosted Detection
- If email footer shows `Current Plan: premium` → self-hosted user
- If no footer or shows pro/team/sandbox → SaaS user
- If unclear → assume SaaS

---

## Steps by Sub-type

### cant_login (can't log in)

**Step: initial**
1. Check if user is an education/school email user (e.g., .ac.jp, .edu, .edu.cn, .ac.uk, etc.)
2. If user IS an edu user AND mentions can't receive verification code:
   - Call `front_create_draft` with "edu email expired check" template (ask if school email has expired, e.g. graduated)
   - Call `state_set` with step="awaiting_email_expired_confirmation", sub_type="cant_login"
3. If user mentions they are a Pro/Team user (non-edu):
   - Call `front_create_draft` with "processing, please wait" template
   - Call `front_forward_to_limin` with conversation_id and message "付费用户登录问题 - [email]"
   - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"
4. If user is NOT paid or unclear:
   - Call `front_create_draft` asking if they are a Pro/Team user, noting this is a paid feature
   - Call `state_set` with step="awaiting_paid_confirmation", sub_type="cant_login"

**Step: awaiting_email_expired_confirmation** (edu user replied about email expiration)
1. Check user's reply — did they confirm their school email has expired (e.g., graduated)?
2. If YES (email expired):
   - Call `front_create_draft` with identity verification request template (need proof of original email ownership)
   - Call `state_set` with step="awaiting_identity_verification", sub_type="email_expired_graduated"
3. If NO (email still works, issue is elsewhere):
   - Call `front_forward_to_limin` with conversation_id and message "edu用户登录问题(非邮箱过期) - [email]"
   - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"

**Step: awaiting_paid_confirmation** (user replied about paid status)
1. Check user's reply — do they confirm they are a Pro/Team user?
2. If YES (paid user):
   - Call `front_create_draft` with "processing, please wait" template
   - Call `front_forward_to_limin` with conversation_id and message "付费用户登录问题 - [email]"
   - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"
3. If NO (free user):
   - Check if email footer shows `Current Plan: premium` → self-hosted user:
     - Call `front_create_draft` with self-hosted can't help template
     - Call `state_set` with step="done", sub_type="cant_login"
   - Otherwise → SaaS free user:
     - Call `front_create_draft` with "processing, please wait" template
     - Call `front_forward_to_limin` with conversation_id and message "免费SaaS用户登录问题 - [email]"
     - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"

**登录问题可能的原因 (for AI to determine sub-type):**
- 收不到验证码
- 忘记密码
- 邮箱过期/失效（毕业等）
- 账号被封/黑名单
- 技术故障

**For email expiration issues (邮箱过期/失效):**
- 需要用户证明原邮箱是本人的（发送确认邮件或提供证明）
- 验证后建 Linear 工单：title "邮箱失效/过期 - [原邮箱] → [新邮箱]", type: account transfer
- 通知 Bobby

### delete_account
**Step: initial**
1. First check if user mentions they can still log in to their account:
   - **If user can log in**: Call `front_create_draft` with self-service deletion template
   - **If user cannot log in** (or unclear): Call `front_create_draft` with identity verification request template, call `state_set` with step="awaiting_identity_verification", sub_type="delete_account", waiting=true, leave conversation open

**Step: awaiting_identity_verification** (user has replied)
1. Check if user's reply confirms identity (sent from original email, or provided proof)
2. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "Account deletion request - [email]" and description
   - Call `front_create_draft` with "received, forwarded to team" template
   - Call `state_set` with step="draft_created"
3. If not confirmed: Call `front_create_draft` asking again politely

### transfer_account / change_email
**Step: initial**
1. First check if user mentions they can still log in to their account:
   - **If user can log in**: Call `front_create_draft` with self-service transfer template
   - **If user cannot log in** (or unclear): Call `front_create_draft` with identity verification request template, call `state_set` with step="awaiting_identity_verification", sub_type="transfer_account", waiting=true

**Step: awaiting_identity_verification**
1. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "Account transfer request - [original email] → [new email]" and description
   - Call `front_create_draft` with "received, forwarded to team" template
   - Call `state_set` with step="draft_created"

### account_anomaly (quota wrong, plan changed unexpectedly)

**SaaS user:**
1. Call `linear_create_ticket` with conversation_id, title "Account anomaly - [email]" and description
2. Call `front_create_draft` with "received, forwarded to team" template
3. Call `state_set` with step="draft_created"

**Self-hosted user:**
1. Call `front_reply_with_template`
2. Call `front_close_conversation`

### account_hacked

**SaaS user:**
1. Call `linear_create_ticket` with conversation_id, title "Account compromised - [email]" and description
2. Call `front_create_draft` with "received, investigating urgently" template
3. Call `state_set` with step="draft_created"

**Self-hosted user:**
1. Call `front_reply_with_template`
2. Call `front_close_conversation`

### merge_accounts
1. Call `front_create_draft` explaining this feature is not currently available

---

## Reply Templates

### Delete account self-service (user can log in)
```
Dear Valued Customer,

Thank you for reaching out.

You can delete your account directly from within your Dify account. Please click on your profile avatar → Account → Delete Account.

Please note that account deletion is permanent and cannot be undone.

If you have any trouble finding this option, feel free to reply and we'll guide you through it.

Best regards,
Dify Support Team
```

### Transfer/Change email self-service (user can log in)
```
Dear Valued Customer,

Thank you for reaching out.

You can change your account email directly within Dify. Please click on your profile avatar → Account → Change Email, and follow the steps provided.

If you encounter any issues during the process, feel free to reply and we'll assist you.

Best regards,
Dify Support Team
```

### Identity verification request
```
Dear Valued Customer,

Thank you for contacting Dify Support.

To protect your account security, we need to verify your identity before proceeding. Could you please do one of the following?

1. Send us a reply from the email address associated with your Dify account, or
2. Provide proof that the email address belongs to you

Once we've verified your identity, we'll process your request as quickly as possible.

Thank you for your patience and understanding.

Best regards,
Dify Support Team
```

### Received, forwarded to team
```
Dear Valued Customer,

Thank you for confirming. We've received your request and have forwarded it to our account management team for processing.

We'll follow up with you once the action has been completed. This typically takes 1–3 business days.

Thank you for your patience.

Best regards,
Dify Support Team
```

### Merge accounts — not available
```
Dear Valued Customer,

Thank you for reaching out.

Unfortunately, account merging is not currently a supported feature on Dify. We've noted your request and will pass it along to our product team for consideration.

If there's anything else we can help you with, please don't hesitate to ask.

Best regards,
Dify Support Team
```

### Self-hosted can't help
```
Dear Valued Customer,

Thank you for reaching out. For self-hosted deployments, account and login issues need to be managed by your own team as Dify does not have access to your self-hosted instance.

If you have any other questions, feel free to reach out.

Best regards,
Dify Support Team
```

### Login troubleshooting (SaaS user - not verification code)
```
Dear Valued Customer,

Thank you for reaching out. To help you with your login issue, please try the following:

1. Check your spam/junk folder for any emails from Dify
2. Make sure you're using the correct email address associated with your Dify account
3. Try clearing your browser cache and cookies, then attempt to log in again
4. If you're using a corporate email, make sure Dify emails aren't blocked by your organization's email filter

If the issue persists after trying these steps, please let us know and we'll assist you further.

Best regards,
Dify Support Team
```

### Processing, please wait (for SaaS users)
```
Dear Valued Customer,

Thank you for contacting us. We're looking into your account issue and will get back to you shortly.

Please note that our team may need to verify your account status. We appreciate your patience.

Best regards,
Dify Support Team
```

### Account hacked — urgent acknowledgment
```
Dear Valued Customer,

Thank you for alerting us. We take account security very seriously.

We've escalated your case to our security team and will investigate this urgently. Please also consider changing your password immediately if you still have access to your account.

We'll be in touch as soon as possible.

Best regards,
Dify Support Team
```
