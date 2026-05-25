# Skill: Account Issues


## Purpose
Handle account-related requests: login issues, account deletion, transfer, email change, anomalies, hacked accounts, and merge requests.

## SaaS vs Self-hosted Detection
- If email footer shows `Current Plan: premium` → self-hosted user
- If no footer or shows pro/team/sandbox → SaaS user
- If unclear → assume SaaS

---

## Steps by Sub-type

### cant_login (can't log in / not receiving verification code)

**SaaS user:**
1. Call `linear_create_ticket` with title "Account login issue - [email]" and description
2. Call `front_reply_with_template`
3. Call `front_close_conversation`

**Self-hosted user:**
1. Call `front_reply_with_template`
2. Call `front_close_conversation`

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
   - Call `state_set` with step="ticket_created"
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
   - Call `state_set` with step="ticket_created"

### account_anomaly (quota wrong, plan changed unexpectedly)

**SaaS user:**
1. Call `linear_create_ticket` with conversation_id, title "Account anomaly - [email]" and description
2. Call `front_create_draft` with "received, forwarded to team" template
3. Call `state_set` with step="ticket_created"

**Self-hosted user:**
1. Call `front_reply_with_template`
2. Call `front_close_conversation`

### account_hacked

**SaaS user:**
1. Call `linear_create_ticket` with conversation_id, title "Account compromised - [email]" and description
2. Call `front_create_draft` with "received, investigating urgently" template
3. Call `state_set` with step="ticket_created"

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

### Account hacked — urgent acknowledgment
```
Dear Valued Customer,

Thank you for alerting us. We take account security very seriously.

We've escalated your case to our security team and will investigate this urgently. Please also consider changing your password immediately if you still have access to your account.

We'll be in touch as soon as possible.

Best regards,
Dify Support Team
```
