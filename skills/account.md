# Skill: Account Issues


## Purpose
Handle account-related requests: login issues, account deletion, transfer, email change, anomalies, hacked accounts, and merge requests.

## SaaS vs Self-hosted Detection
- If email footer shows `Current Plan: premium` → self-hosted user
- If footer shows pro/team/sandbox or user explicitly says Dify Cloud/SaaS → SaaS user
- If unclear for login issues → do NOT assume SaaS; ask whether they use Dify Cloud/SaaS or self-hosted, and ask their plan

---


## Tool Sequencing and Hard Stops
- For every handoff that requires Linear, wait for `linear_create_ticket` to return the real URL before calling `front_forward_to_bobby` or `feishu_notify_sybil_group`.
- Never leave placeholder URL text in tool arguments. Replace it with the exact Linear URL returned by the previous tool call.
- Any draft that asks the user to confirm identity, deployment type, plan, original email ownership, or other missing information must be followed by `state_set` with `waiting=true`.
- For SaaS handoffs, final `state_set` payload should include the Linear URL and the key account email(s) when known.
- If the user is self-hosted, Community Edition, or `Current Plan: premium`, do not create Linear for SaaS account access; create a draft explaining Dify cannot access self-hosted deployments.


## Draft Quality Bar
- Start with a complete, authoritative English version; never create a local-language-only customer draft.
- If the latest customer message is primarily non-English, finish the English version first, then write exactly `For reference, a <Language> translation is provided below.` and add a faithful matching-language version.
- Front automatically appends the configured default signature. Do not put `Best regards,`, `Dify Support Team`, `Cheers`, a personal name, or any other manual sign-off in the draft body; keep every language block unsigned.
- If the customer wrote in English, do not add a second language version.
- For approved deterministic templates marked verbatim, preserve the English body exactly; for a non-English customer, append only the required reference notice and a faithful matching-language translation.
- Answer only what the email supports. Do not invent product behavior, policy exceptions, timelines, refunds, eligibility, or engineering commitments.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an issue is fixed, approved, refunded, or escalated unless a tool result or policy explicitly proves it.
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps by Sub-type

### account_suspended

For a first account-level suspension, ban, block, or enforcement appeal with no linked same-sender history, use the one approved English response handled deterministically before this skill runs. Preserve the standardized English body exactly, and for a non-English customer append only the required reference notice and faithful matching-language translation. Do not add a manual sign-off to either body block.

If the same normalized sender already has a suspension or appeal in another Front conversation, treat the new thread as a continuation. Do not create the standardized draft again and do not create another Linear ticket. The runtime must cross-link the current and canonical conversations with internal comments, preserve any existing Linear URL, and save the new conversation as `manual_review`.

### cant_login (can't log in)

**Step: initial**
1. Check if user is an education/school email user (e.g., .ac.jp, .edu, .edu.cn, .ac.uk, etc.)
2. If user IS an edu user AND mentions can't receive verification code:
   - Call `front_create_draft` with "edu email expired check" template (ask if school email has expired, e.g. graduated)
   - Call `state_set` with step="awaiting_email_expired_confirmation", sub_type="cant_login", waiting=true
3. If the email clearly indicates self-hosted, Community Edition, open-source deployment, or `Current Plan: premium`:
   - Call `front_create_draft` with self-hosted can't help template
   - Call `state_set` with step="draft_created", sub_type="cant_login"
4. If the email clearly indicates Dify Cloud/SaaS (for example `Current Plan: professional`, `Current Plan: team`, `Current Plan: sandbox`, or the user says they use cloud.dify.ai):
   - Call `linear_create_ticket` with conversation_id, title "SaaS login issue - [email]", sender_email, original_message, and description containing plan, issue, and login email. Fill actual values.
   - WAIT for `linear_create_ticket` to return the URL.
   - Call `front_forward_to_bobby` with conversation_id and message "SaaS 登录问题，请处理。发件人: <actual email>. 计划: <actual plan>. 摘要: <brief summary>. Linear: <exact returned Linear URL>".
   - Call `front_create_draft` with "processing, please wait" template
   - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"
5. If deployment type or plan is unclear:
   - Call `front_create_draft` with "ask deployment and plan" template. Ask whether they use Dify Cloud/SaaS or self-hosted, and ask their current plan. Explain that Dify Support can investigate SaaS login issues, but cannot access self-hosted deployments.
   - Call `state_set` with step="awaiting_deployment_and_plan_confirmation", sub_type="cant_login", waiting=true

**Step: awaiting_email_expired_confirmation** (edu user replied about email expiration)
1. Check user's reply — did they confirm their school email has expired (e.g., graduated)?
2. If YES (email expired):
   - Call `front_create_draft` with identity verification request template (need proof of original email ownership)
   - Call `state_set` with step="awaiting_identity_verification", sub_type="email_expired_graduated", waiting=true
3. If NO (email still works, issue is elsewhere):
   - Call `front_forward_to_bobby` with conversation_id and message "edu用户登录问题(非邮箱过期) - [email]"
   - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"

**Step: awaiting_deployment_and_plan_confirmation** (user replied with deployment type or plan)
1. If the reply confirms self-hosted, Community Edition, open-source deployment, or `Current Plan: premium`:
   - Call `front_create_draft` with self-hosted can't help template
   - Call `state_set` with step="draft_created", sub_type="cant_login"
2. If the reply confirms Dify Cloud/SaaS, Sandbox, Pro, Team, or cloud.dify.ai:
   - Call `linear_create_ticket` with conversation_id, title "SaaS login issue - [email]", sender_email, original_message, and description containing plan, issue, and login email. Fill actual values.
   - WAIT for `linear_create_ticket` to return the URL.
   - Call `front_forward_to_bobby` with conversation_id and message "SaaS 登录问题，请处理。发件人: <actual email>. 计划: <actual plan>. 摘要: <brief summary>. Linear: <exact returned Linear URL>".
   - Call `front_create_draft` with "processing, please wait" template
   - Call `state_set` with step="forwarded_keep_open", sub_type="cant_login"
3. If the reply still does not clarify SaaS vs self-hosted:
   - Call `front_create_draft` asking again for deployment type and current plan
   - Keep state as `awaiting_deployment_and_plan_confirmation`

**Step: awaiting_paid_confirmation** (legacy state name)
- Treat this exactly the same as `awaiting_deployment_and_plan_confirmation`.

**登录问题可能的原因 (for AI to determine sub-type):**
- 收不到验证码
- 忘记密码
- 邮箱过期/失效（毕业等）
- 账号被封/黑名单
- 技术故障

**For email expiration issues (邮箱过期/失效):**
- 需要用户证明原邮箱是本人的（发送确认邮件或提供证明）
- 验证后建 Linear 工单：title "邮箱失效/过期 - [原邮箱] → [新邮箱]", type: account transfer
- 建 Linear 后通过 `front_forward_to_bobby` 转给 Bobby，message 必须包含 Linear 链接和摘要

### delete_account
**Step: initial**
1. First check if user mentions they can still log in to their account:
   - **If user can log in**: Call `front_create_draft` with self-service deletion template
   - **If user cannot log in** (or unclear): Call `front_create_draft` with identity verification request template, call `state_set` with step="awaiting_identity_verification", sub_type="delete_account", waiting=true, leave conversation open

**Step: awaiting_identity_verification** (user has replied)
1. Check if user's reply confirms identity (sent from original email, or provided proof)
2. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "Account deletion request - [email]" and description
   - WAIT for `linear_create_ticket` to return the URL.
   - Call `front_forward_to_bobby` with conversation_id and message "账号删除请求，请处理。发件人: <actual email>. 摘要: <brief summary>. Linear: <exact returned Linear URL>".
   - Call `front_create_draft` with "received, forwarded to team" template
   - Call `state_set` with step="forwarded_keep_open", sub_type="delete_account"
3. If not confirmed: Call `front_create_draft` asking again politely, then call `state_set` with step="awaiting_identity_verification", sub_type="delete_account", waiting=true

### transfer_account / change_email
**Step: initial**
1. First check if user mentions they can still log in to their account:
   - **If user can log in**: Call `front_create_draft` with self-service transfer template
   - **If user cannot log in** (or unclear): Call `front_create_draft` with identity verification request template, call `state_set` with step="awaiting_identity_verification", sub_type="transfer_account", waiting=true

**Step: awaiting_identity_verification**
1. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "Account transfer request - [original email] → [new email]" and description
   - WAIT for `linear_create_ticket` to return the URL.
   - Call `front_forward_to_bobby` with conversation_id and message "账号转移/换邮箱请求，请处理。原邮箱: <actual original email>, 新邮箱: <actual new email>. 摘要: <brief summary>. Linear: <exact returned Linear URL>".
   - Call `front_create_draft` with "received, forwarded to team" template
   - Call `state_set` with step="forwarded_keep_open", sub_type="transfer_account"

### account_anomaly (quota wrong, plan changed unexpectedly)

**SaaS user:**
1. Call `linear_create_ticket` with conversation_id, title "Account anomaly - [email]", sender_email, original_message, and description containing plan, workspace, issue, and billing evidence. Fill actual values.
2. WAIT for `linear_create_ticket` to return the URL.
3. Call `feishu_notify_sybil_group` with conversation_id, cc_email="bobby@dify.ai", handoff_type="account_anomaly", linear_url set to the exact Linear URL returned above, and message "类型: account_anomaly。账号额度/计划异常，请处理。发件人: <actual email>. 计划: <actual plan>. 摘要: <brief summary>. Linear: <exact returned Linear URL>".
4. Call `front_create_draft` with "received, forwarded to team" template.
5. Call `state_set` with step="forwarded_keep_open", sub_type="account_anomaly".

**Self-hosted user:**
1. Call `front_create_draft` with self-hosted can't help template
2. Call `state_set` with step="draft_created", sub_type="account_anomaly"

### account_hacked

**SaaS user:**
1. Call `linear_create_ticket` with conversation_id, title "Account compromised - [email]", sender_email, original_message, and description containing compromise evidence and urgency. Fill actual values.
2. WAIT for `linear_create_ticket` to return the URL.
3. Call `front_forward_to_bobby` with conversation_id and message "账号疑似被盗/异常访问，请优先处理。发件人: <actual email>. 摘要: <brief summary>. Linear: <exact returned Linear URL>".
4. Call `front_create_draft` with "received, investigating urgently" template.
5. Call `state_set` with step="forwarded_keep_open", sub_type="account_hacked".

**Self-hosted user:**
1. Call `front_create_draft` with self-hosted can't help template
2. Call `state_set` with step="draft_created", sub_type="account_hacked"

### merge_accounts
1. Call `front_create_draft` explaining this feature is not currently available
2. Call `state_set` with step="draft_created", sub_type="merge_accounts"

---

## Reply Templates

### Delete account self-service (user can log in)
```
Dear Valued Customer,

Thank you for reaching out.

You can delete your account directly from within your Dify account. Please click on your profile avatar → Account → Delete Account.

Please note that account deletion is permanent and cannot be undone.

If you have any trouble finding this option, feel free to reply and we'll guide you through it.

```

### Transfer/Change email self-service (user can log in)
```
Dear Valued Customer,

Thank you for reaching out.

You can change your account email directly within Dify. Please click on your profile avatar → Account → Change Email, and follow the steps provided.

If you encounter any issues during the process, feel free to reply and we'll assist you.

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

```

### Received, forwarded to team
```
Dear Valued Customer,

Thank you for confirming. We've received your request and have forwarded it to our account management team for processing.

We'll follow up with you once the action has been completed. This typically takes 1–3 business days.

Thank you for your patience.

```

### Merge accounts — not available
```
Dear Valued Customer,

Thank you for reaching out.

Unfortunately, account merging is not currently a supported feature on Dify. We've noted your request and will pass it along to our product team for consideration.

If there's anything else we can help you with, please don't hesitate to ask.

```

### Self-hosted can't help
```
Dear Valued Customer,

Thank you for reaching out. For self-hosted deployments, account and login issues need to be managed by your own team as Dify does not have access to your self-hosted instance.

If you have any other questions, feel free to reach out.

```

### Ask deployment and plan
```
Dear Valued Customer,

Thank you for reaching out. To check this login issue correctly, could you please confirm the following?

1. Are you using Dify Cloud/SaaS, or a self-hosted Dify deployment?
2. What is your current plan? For example: Sandbox, Pro, Team, Premium, or Community Edition.
3. What email address are you trying to log in with?

Please note that Dify Support can investigate login issues for Dify Cloud/SaaS accounts. For self-hosted deployments, we cannot access your instance or account system, so login issues need to be handled by your own deployment administrator.

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

```

### Processing, please wait (for SaaS users)
```
Dear Valued Customer,

Thank you for contacting us. We're looking into your account issue and will get back to you shortly.

Please note that our team may need to verify your account status. We appreciate your patience.

```

### Account hacked — urgent acknowledgment
```
Dear Valued Customer,

Thank you for alerting us. We take account security very seriously.

We've escalated your case to our security team and will investigate this urgently. Please also consider changing your password immediately if you still have access to your account.

We'll be in touch as soon as possible.

```
