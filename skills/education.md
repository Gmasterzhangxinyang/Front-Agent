# Skill: Education Plan

## Purpose
Handle education plan applications, rejections, discount and credit-allowance issues, and account suspensions.

## Key Facts
- Education discount: 100% off, valid for 1 year
- It applies only to the yearly Professional plan
- Eligibility must be verified again each year
- The applicant must be at least 18 and be a current student, teacher, or education staff member
- Only higher education institutions (universities, colleges, government-accredited) qualify
- K-12 schools and unaccredited institutions do NOT qualify
- The user must register Dify Cloud with a school-issued educational email, not a personal address such as Gmail or Yahoo
- For an active Education Plan application, rejection, verification, or discount review, the actual `From` address of the inbound message must be the applicant's school-issued email and must match the school email claimed or registered for the application. A school address written only in the body, signature, CC, screenshot, or forwarded text does not verify ownership.
- Official self-service application path: register at `https://cloud.dify.ai` with the school email -> **Settings** -> **Billing** -> **Get Education Verified** -> enter the full school name and role -> after approval select the workspace -> **Use education discount** -> choose yearly Professional and complete activation
- The included Education Plan message-credit allowance is now 200 message credits in total, with no monthly reset; it was previously 5,000 message credits per month
- This allowance change applies only to included message credits; all other Professional plan features and resource entitlements remain available at no cost
- After the included credits are used, users can continue using models by configuring their own API key from a supported model provider
- A workspace shown as Sandbox or Free, rather than Professional with the 200-message-credit allowance, is a separate issue that should be investigated
- Official documentation: `https://docs.dify.ai/en/cloud/use-dify/workspace/subscription-management#dify-for-education`


## Tool Sequencing and Hard Stops
- Before creating or continuing an Education review, compare the actual sender email supplied by the runtime with the claimed or registered school email. This identity gate applies to active applications, rejections, verification failures, and discount reviews; the expired-school-email/graduation recovery flow uses its separate proof policy.
- If the actual sender is a personal address or does not exactly match the claimed or registered school email, do not call `linear_create_ticket`, do not notify Sybil, and do not say the application was received or forwarded for review. Create only the **Send from school email** draft and call `state_set` with step=`awaiting_school_email_sender_verification`, waiting=true, preserving the claimed school email and actual sender in the payload.
- If a review ticket already exists before the mismatch is noticed, preserve its `linear_url`, add a concise internal Front comment that identity verification is pending, and do not create a duplicate ticket or continue the review until a new request arrives directly from the school-issued address.
- Never call `feishu_notify_sybil_group` before `linear_create_ticket` has returned a real Linear URL.
- Never leave placeholder URL text in tool arguments. Use the exact URL returned by `linear_create_ticket`.
- For successful education reviews, call tools in this order: `linear_create_ticket` -> `feishu_notify_sybil_group` -> `front_create_draft` -> `state_set`.
- The final `state_set` payload for successful reviews should include `school_name`, `school_domain`, and `linear_url`.
- If asking the user for more information or proof, call `state_set` with `waiting=true`.
- If the current step is `forwarded_keep_open` or saved data already contains `linear_url`, a review ticket already exists. Never call `linear_create_ticket` again. The runtime will block it even if requested.
- A follow-up to an existing review may reuse only the exact saved `linear_url` for `feishu_notify_sybil_group`; never create or guess a replacement URL.


## Reply Continuation Policy
- Treat the latest user reply as authoritative for the next step. Do not blindly repeat the previous draft.
- For `awaiting_school_email_sender_verification`, do not treat an address repeated in the body or signature as proof. Continue to wait for a new inbound request whose actual `From` address is the claimed school-issued email. Do not create or continue an internal review from the personal-email thread.
- A user may switch among education intents within the same conversation. When the latest reply clearly reports rejection, missing discount, a 200-message-credit Education allowance question, expired school email/graduation, cancellation, or an Education account suspension, follow that sub-type and save the new `sub_type`.
- For `awaiting_school_info` and `awaiting_identity_verification`, use the newest reply together with the saved payload. Preserve previously collected facts when calling `state_set`.
- For `draft_created`:
  - Answer a new education question with a concise draft that follows the English-first and reference-translation policy in the Draft Quality Bar.
  - If the user reports that verification or activation succeeded, create a brief acknowledgment draft; do not create a Linear ticket or notify Sybil.
  - Save the resulting education sub-type and keep step=`draft_created` unless another defined step applies.
- For `forwarded_keep_open`, or whenever saved data contains `linear_url`:
  1. Never call `linear_create_ticket` again.
  2. If the reply contains material new information, call `front_add_comment` with a concise internal summary of only the new facts.
  3. For material review information, call `feishu_notify_sybil_group` with handoff_type=`education_review_followup`, the exact saved `linear_url`, and a concise Chinese summary. This creates at most one follow-up digest item for that review.
  4. Call `front_create_draft` acknowledging receipt and saying the information has been added for review. Do not expose the Linear URL or internal routing.
  5. Call `state_set` with step=`forwarded_keep_open`, waiting=false, and preserve the existing `school_name`, `school_domain`, `linear_url`, and other saved data.
  6. If the reply only says thanks and contains no new facts, create a brief acknowledgment draft and preserve the same state without another internal notification.


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

## Steps by Sub-Type

### how_to_apply (asks how to get or use the Education Plan)

**Step: initial or draft_created**
1. Call `front_create_draft` with the self-service application template, following the English-first and reference-translation policy in the Draft Quality Bar.
2. Do not create a Linear ticket or notify Sybil for a general how-to-apply question.
3. Call `state_set` with category=`education`, sub_type=`how_to_apply`, step=`draft_created`, waiting=false.
4. If the user later reports a rejection, missing discount, expired school email, or cancellation, follow the matching sub-type under the Reply Continuation Policy.

### rejected (education plan application rejected)

**Step: initial**
1. **First, enforce the school-email sender identity gate.** Compare the actual runtime sender address with the school email claimed or registered for the application. If the sender is personal or mismatched, use the **Send from school email** template, set step=`awaiting_school_email_sender_verification` with waiting=true, and stop. Do not create or continue a review.
2. Check if the user has already provided school information in their email (school name and email domain).
3. If school info is provided:
   - Extract: school full name (English) and school email domain
   - If user provided personal email (Gmail, Yahoo, etc.) instead of school domain:
     - Call `front_create_draft` with the **Send from school email** template
     - Call `state_set` with step="awaiting_school_info", waiting=true
   - Determine school type:
     - **Higher education (university/college, government-accredited):**
       - Call `linear_create_ticket` with conversation_id, title "教育版 - [school name]", sender_email (the user's email address), original_message (the user's original email text), and description — fill in actual values, never use placeholder text:
         ```
         **学校全名：** <actual school full name in English>

         **邮箱域名：** <actual email domain>

         **AI 评估：** <your actual assessment, e.g. "Higher education institution, government-accredited" or "Likely accredited university">
         ```
       - WAIT for `linear_create_ticket` to return the URL before proceeding
       - Call `feishu_notify_sybil_group` with conversation_id, handoff_type="education_review", linear_url set to the exact Linear URL returned above, and message "类型: education_review。请审核教育版申请。学校: <actual school name>, 域名: <actual domain>. Linear: <exact returned Linear URL>". Never leave placeholder text in the tool arguments.
       - Call `front_create_draft` with "received, forwarding to team" template
       - Call `state_set` with step="forwarded_keep_open"
     - **K-12 or unaccredited:**
       - Call `front_create_draft` with "not eligible" template
       - Call `state_set` with step="draft_created"
4. If school info is NOT provided:
   - Call `front_create_draft` with "please provide school info" template
   - Call `state_set` with step="awaiting_school_info", waiting=true

**Step: awaiting_school_info** (user has replied with school info)
1. First enforce the same school-email sender identity gate. A school email shown only in the reply body or signature is not sufficient. If the actual sender is personal or mismatched, use the **Send from school email** template, set step=`awaiting_school_email_sender_verification` with waiting=true, and stop.
2. Extract: school full name (English) and school email domain from user's reply
3. If user provided personal email (Gmail, Yahoo, etc.) instead of school domain:
   - Call `front_create_draft` with the **Send from school email** template
   - Call `state_set` with step="awaiting_school_info", waiting=true
4. Determine school type:
   - **Higher education (university/college, government-accredited):**
     - Call `linear_create_ticket` with conversation_id, title "教育版 - [school name]", sender_email (the user's email address), original_message (the user's original email text), and description — fill in actual values, never use placeholder text:
       ```
       **学校全名：** <actual school full name in English>

       **邮箱域名：** <actual email domain>

       **AI 评估：** <your actual assessment, e.g. "Higher education institution, government-accredited" or "Likely accredited university">
       ```
     - WAIT for `linear_create_ticket` to return the URL before proceeding
     - Call `feishu_notify_sybil_group` with conversation_id, handoff_type="education_review", linear_url set to the exact Linear URL returned above, and message "类型: education_review。请审核教育版申请。学校: <actual school name>, 域名: <actual domain>. Linear: <exact returned Linear URL>". Never leave placeholder text in the tool arguments.
     - Call `front_create_draft` with "received, forwarding to team" template
     - Call `state_set` with step="forwarded_keep_open"
   - **K-12 or unaccredited:**
     - Call `front_create_draft` with "not eligible" template
     - Call `state_set` with step="draft_created"

### credit_allowance_200 (Education Plan shows only 200 message credits)

**Step: initial or draft_created**
1. Use this branch when a user asks why an activated or subscribed Education Plan has only 200 message credits, whether those credits reset monthly, or why the former 5,000-per-month allowance is no longer present.
2. Call `front_create_draft` with the **Education 200-message-credit allowance** template below as the authoritative unsigned English body. If the latest customer message is primarily non-English, append the required reference notice and faithful translation.
3. Do not create a Linear ticket or notify Sybil for the normal 200-credit allowance.
4. Call `state_set` with category=`education`, sub_type=`credit_allowance_200`, step=`draft_created`, waiting=false.
5. Do not mention any workspace refresh date or August 10. If the workspace itself is displayed as Sandbox or Free rather than Professional with 200 message credits, treat that as a separate issue for investigation.

### no_discount (edu verified but discount not showing)

**Step: initial**
1. First check whether the user says the education discount/qualification is already verified but activation is blocked by credit card binding, no supported international credit card, regional card restrictions, or asks support to manually bypass card binding.
   - Policy: card binding cannot be bypassed. If the user has no supported international credit card, they cannot complete the Education Plan activation at this time.
   - Do NOT create Linear tickets for this case.
   - Do NOT notify Sybil for this case.
   - Call `front_create_draft` with "card binding cannot be bypassed" template.
   - Call `state_set` with step="draft_created".
2. Check if user mentions they can see the "edu" badge in their account.
3. If they see the edu badge but no discount:
   - Call `front_create_draft` with billing guidance template
   - Call `state_set` with step="draft_created"
4. If they do not see the edu badge (not verified):
   - Call `front_create_draft` with "please provide school info" template
   - Call `state_set` with step="awaiting_school_info", waiting=true

**Step: awaiting_school_info** (user replied with school info after no_discount)
- Follow the same logic as `rejected` -> `awaiting_school_info` step above

### email_expired_graduated (graduated, school email no longer works)

**Step: initial**
1. Use this account-recovery flow only when the user wants to regain access, change the account email, or recover an account tied to the unavailable school email.
2. If the user instead asks to cancel a trial/subscription or avoid being billed, do not assume they need account recovery. Follow `cancel_subscription` below, including its Education Plan confirmation gate.
3. User mentions they graduated or their school email is no longer accessible.
4. Call `front_create_draft` with identity verification request template (need proof the original email was theirs).
5. Call `state_set` with step="awaiting_identity_verification", sub_type="email_expired_graduated", waiting=true.

**Step: awaiting_identity_verification** (user replied with proof)
1. Check if user's reply provides sufficient proof (sent from original email, or provided other proof of identity)
2. If confirmed:
   - Call `linear_create_ticket` with conversation_id, title "教育版邮箱失效/毕业 - [原邮箱] → [新邮箱]", sender_email (the user's email address), original_message (the user's original email text), and description:
     ```
     **原邮箱：** <original school email that no longer works>

     **新邮箱：** <user's new email>

     **原因：** 毕业/邮箱失效

     **证明：** <summary of proof provided by user>
     ```
   - WAIT for `linear_create_ticket` to return the real URL before proceeding
   - Call `feishu_notify_sybil_group` with conversation_id, handoff_type="education_email_expired", linear_url set to the exact Linear URL returned above, and message "类型: education_email_expired。教育版用户邮箱失效（毕业）- 原邮箱: <actual original email>, 新邮箱: <actual new email>. Linear: <exact returned Linear URL>". Never leave placeholder text in the tool arguments.
   - Call `front_create_draft` with "received, forwarding to team" template
   - Call `state_set` with step="forwarded_keep_open"
3. If not confirmed: Call `front_create_draft` asking again politely for proof, then call `state_set` with step="awaiting_identity_verification", sub_type="email_expired_graduated", waiting=true

### cancel_subscription (education plan user wants to cancel)

**Step: initial**
1. First determine whether the user explicitly confirms that the affected trial/subscription is the Dify Education Plan (for example, they say Education Plan, student plan, education discount, or Education Verified).
2. If the user explicitly confirms it is the Education Plan:
   - Call `front_create_draft` with the no-auto-renew explanation template.
   - Call `state_set` with step="draft_created", sub_type="cancel_subscription", waiting=false.
3. If the user only mentions a school/university email, graduation, or a generic Dify trial/subscription and has not confirmed the plan type:
   - Do not infer that the subscription is an Education Plan merely from the email domain or graduation context.
   - Do not request identity proof or account-ownership evidence.
   - Do not give paid-plan cancellation steps and do not yet state that the subscription will not renew.
   - Call `front_create_draft` with the **Confirm Education Plan** template below.
   - Call `state_set` with category="education", sub_type="cancel_subscription", step="awaiting_plan_type_confirmation", waiting=true, and payload containing `plan_type="unconfirmed"`.

**Step: awaiting_plan_type_confirmation**
1. If the user confirms it was the Education Plan, call `front_create_draft` with the no-auto-renew explanation template, then call `state_set` with step="draft_created", sub_type="cancel_subscription", waiting=false, and payload containing `plan_type="education"`.
2. If the user confirms it was a standard paid trial/subscription rather than the Education Plan, call `front_create_draft` with the exact Dify Cloud cancellation path: current workspace name in the upper-left corner -> **Settings** -> **Billing** -> **Billing and Subscriptions** -> **Manage** -> select the active subscription -> **Cancel plan** -> confirm. Then call `state_set` with category="billing", sub_type="downgrade", step="draft_created", waiting=false, and payload containing `plan_type="standard_paid"`.
3. If the reply still does not identify the plan type, ask the same minimum confirmation question and keep step="awaiting_plan_type_confirmation", waiting=true.

### account_suspended (Education Plan/Education Verified account suspended or banned)

This sub-type is only for an account-level enforcement suspension or ban. An Education Plan application or verification that was rejected, denied, declined, unsuccessful, or not approved remains sub_type=`rejected` and must follow the normal education review flow above.

**Step: any**
1. This template is only for a first-contact suspension with no linked same-sender history. Call `front_create_draft` with the **Account suspension** template below verbatim as the unsigned English body; Front appends its configured default signature.
2. Do not personalize, paraphrase, shorten, or add any promise, timeline, policy explanation, or manual sign-off. If the latest customer message is non-English, preserve the English body exactly and append only the required reference notice and a faithful matching-language translation.
3. Do not create a Linear ticket, notify Sybil, forward the conversation, add an internal handoff, or send a direct customer reply.
4. Call `state_set` with category=`education`, sub_type=`account_suspended`, step=`draft_created`, waiting=false.
5. If the same normalized sender already has a suspension, appeal, supporting evidence, or existing review in another Front conversation, do not repeat the template or create another ticket. Cross-link the conversations with brief internal comments containing only the main/related Front links, existing Linear URL, and duplicate-draft status; do not repeat history or message excerpts. Preserve the existing Linear URL and review context, and set the new thread to `manual_review`.

## Reply Templates

### Self-service application
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify's Education Plan.

You can apply through Dify Cloud using these steps:

1. Register or sign in at https://cloud.dify.ai with your school-issued educational email.
2. Go to **Settings** -> **Billing**.
3. Select **Get Education Verified**, then enter your school's full name and your role.
4. After verification is approved, select the workspace where you want to use the benefit and click **Use education discount**.
5. Choose the yearly **Professional** plan and complete the activation process. The 100% education discount applies to this yearly plan.

Please note:

- Applicants must be at least 18 and be a current student, teacher, or education staff member.
- A school-issued educational email is required; personal email addresses are not eligible for verification.
- Eligibility must be verified again each year.

Official guide: https://docs.dify.ai/en/cloud/use-dify/workspace/subscription-management#dify-for-education

```

### Request school info
⚠️ 需确认: 语气是否合适？
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify's Education Plan!

To process your application, could you please provide the following information?

1. Your school's full name in English
2. Your school's official email domain (e.g., @university.edu)

Please note that the education plan is available for higher education institutions (universities and colleges) accredited by government authorities. A school email address is required — personal email addresses (Gmail, Yahoo, etc.) are not accepted.

We look forward to hearing from you!

```

### Send from school email
```
Dear [User's Name / Valued Customer],

Thank you for providing the information.

To verify ownership of the educational email and protect Education Plan benefits, we can only review this request when it is sent directly from the school-issued email address associated with the application.

This message was sent from [actual sender email]. Please send a new email to support@dify.ai from [claimed school email] and include the same details and attachments. A school email address shown only in the message body, signature, CC, screenshot, or forwarded text is not sufficient for verification.

Once we receive the request directly from the school-issued email address, we can review the next step.

```

### Not eligible (K-12 or unaccredited)
⚠️ 需确认: 拒绝理由描述是否合适？
```
Dear [User's Name / Valued Customer],

Thank you for providing your school information.

After reviewing your application, we regret to inform you that [school name] does not currently qualify for Dify's Education Plan. Our education discount is available for higher education institutions (universities and colleges) that are accredited by government authorities.

We understand this may be disappointing, and we appreciate your interest in Dify. You're still welcome to use our free Sandbox plan, or explore our other pricing options at https://dify.ai/pricing.

Thank you for your understanding.

```

### Received, forwarding to team
```
Dear [User's Name / Valued Customer],

Thank you for providing your school information!

We've received your application and have forwarded it to our team for review. We'll get back to you once the verification is complete.


```

### Billing guidance (edu badge visible but no discount)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out!

To apply your education discount, please follow these steps:

1. Go to **Settings** -> **Billing** in your Dify dashboard.
2. Select the workspace where you want to use the benefit.
3. Click **Use education discount**.
4. Choose the yearly **Professional** plan and complete activation.
5. The 100% education discount should be applied to that yearly plan.

Please note that the discount applies only to the yearly Professional plan. It will not appear for monthly billing.

If you've followed these steps and still don't see the discount, please reply and let us know — we'll be happy to investigate further.

```

### Card binding cannot be bypassed
```
Dear [User Name / Valued Customer],

Thank you for reaching out and for sharing the screenshot.

At the moment, Education Plan activation requires completing the payment method / credit card binding step in the dashboard. We are not able to manually bypass this requirement or activate the Professional Education Plan directly from our side.

If you do not have a supported international credit card available, unfortunately you will not be able to complete the Education Plan activation at this time.

Thank you for your understanding.

```

### Identity verification request (for email expired / graduated)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out. We're sorry to hear that your school email is no longer accessible.

To help you with your account, we need to verify that the school email was previously associated with your Dify account. Could you please provide one of the following:

1. A screenshot or confirmation showing your Dify account was registered with your school email, or
2. Any other proof that the school email belonged to you

Once we've verified your identity, we'll assist you in updating your account email.

Thank you for your patience and understanding.

```

### Education 200-message-credit allowance
```
Hi,

Thank you for reaching out.

We recently updated the message credit allowance included with Dify for Education:

Previously: 5,000 message credits per month
Now: 200 message credits in total, with no monthly reset

Please note that this change applies only to the included message credits. Your workspace will continue to have access to all other Professional plan features and resource entitlements at no cost.

This adjustment became necessary due to a significant increase in misuse of education benefits, which made the previous monthly allowance unsustainable. We understand that this change also affects users who have used the program as intended, and we sincerely apologize for any inconvenience it may cause.

Once the included credits have been used, you can continue using models in Dify by configuring your own API key from a supported model provider.

You can find the latest program details in our Dify for Education FAQ.

If your workspace is displayed as Sandbox or Free, rather than Professional with the 200-message-credit allowance, please let us know so we can investigate it separately.

```

### No-auto-renew explanation (for education plan cancel request)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out regarding your education plan subscription.

We'd like to confirm that your Dify education plan will NOT automatically renew after its current term ends. There is no need to take any action to cancel — your subscription will simply expire at the end of the billing period without any further charges.

If you have any other questions, please don't hesitate to reach out.

```

### Confirm Education Plan (when plan type is not stated)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out. Before we provide the correct cancellation and billing guidance, could you please confirm whether the trial or subscription associated with your university email was activated through Dify's Education Plan?

Once you confirm the plan type, we can advise you on the correct next step.

```

### Account suspension
```
Hello,

Following a review of the registration and usage activity associated with your account, we determined that the activity involved coordinated account abuse, circumvention of usage restrictions, or the unauthorized resale or redistribution of Dify services, credits, or access.

Such activity violates the Dify Terms of Service, which require accounts to be used only for authorized purposes, prohibit the transfer or resale of credits and usage entitlements, and allow Dify to suspend accounts whose activity may harm the platform, its services, or other users.

Your account will therefore remain suspended. Attempts to create or use additional accounts to circumvent this suspension may result in those accounts being suspended as well.

If you believe this decision was made in error, you may submit one appeal through our designated support channel using the email address registered to the account. Duplicate or mass appeal requests will not receive separate reviews.

If the account received Education Verified benefits, please also provide valid proof that you are currently enrolled or employed at the institution stated in your application. Providing documentation does not guarantee reinstatement, as we will also review the account’s usage for compliance with the Dify Terms of Service.
```
