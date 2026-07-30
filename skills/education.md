# Skill: Education Plan

## Purpose
Handle education plan applications, rejections, and discount issues.

## Key Facts
- Education discount: 100% off, valid for 1 year
- It applies only to the yearly Professional plan
- Eligibility must be verified again each year
- The applicant must be at least 18 and be a current student, teacher, or education staff member
- Only higher education institutions (universities, colleges, government-accredited) qualify
- K-12 schools and unaccredited institutions do NOT qualify
- The user must register Dify Cloud with a school-issued educational email, not a personal address such as Gmail or Yahoo
- Official self-service application path: register at `https://cloud.dify.ai` with the school email -> **Settings** -> **Billing** -> **Get Education Verified** -> enter the full school name and role -> after approval select the workspace -> **Use education discount** -> choose yearly Professional and complete activation
- Official documentation: `https://docs.dify.ai/en/cloud/use-dify/workspace/subscription-management#dify-for-education`


## Tool Sequencing and Hard Stops
- Never call `feishu_notify_sybil_group` before `linear_create_ticket` has returned a real Linear URL.
- Never leave placeholder URL text in tool arguments. Use the exact URL returned by `linear_create_ticket`.
- For successful education reviews, call tools in this order: `linear_create_ticket` -> `feishu_notify_sybil_group` -> `front_create_draft` -> `state_set`.
- The final `state_set` payload for successful reviews should include `school_name`, `school_domain`, and `linear_url`.
- If asking the user for more information or proof, call `state_set` with `waiting=true`.
- If the current step is `forwarded_keep_open` or saved data already contains `linear_url`, a review ticket already exists. Never call `linear_create_ticket` again. The runtime will block it even if requested.
- A follow-up to an existing review may reuse only the exact saved `linear_url` for `feishu_notify_sybil_group`; never create or guess a replacement URL.


## Reply Continuation Policy
- Treat the latest user reply as authoritative for the next step. Do not blindly repeat the previous draft.
- A user may switch among education intents within the same conversation. When the latest reply clearly reports rejection, missing discount, expired school email/graduation, or cancellation, follow that sub-type and save the new `sub_type`.
- For `awaiting_school_info` and `awaiting_identity_verification`, use the newest reply together with the saved payload. Preserve previously collected facts when calling `state_set`.
- For `draft_created`:
  - Answer a new education question with a new concise draft in the user's language.
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
- Write concise, professional English unless the user wrote primarily in another language.
- Answer only what the email supports. Do not invent product behavior, policy exceptions, timelines, refunds, eligibility, or engineering commitments.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an issue is fixed, approved, refunded, or escalated unless a tool result or policy explicitly proves it.
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps by Sub-Type

### how_to_apply (asks how to get or use the Education Plan)

**Step: initial or draft_created**
1. Call `front_create_draft` with the self-service application template in the user's language.
2. Do not create a Linear ticket or notify Sybil for a general how-to-apply question.
3. Call `state_set` with category=`education`, sub_type=`how_to_apply`, step=`draft_created`, waiting=false.
4. If the user later reports a rejection, missing discount, expired school email, or cancellation, follow the matching sub-type under the Reply Continuation Policy.

### rejected (education plan application rejected)

**Step: initial**
1. **First, check if the user has already provided school information in their email** (school name and email domain)
2. If school info is provided:
   - Extract: school full name (English) and school email domain
   - If user provided personal email (Gmail, Yahoo, etc.) instead of school domain:
     - Call `front_create_draft` with "must use school email" template
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
3. If school info is NOT provided:
   - Call `front_create_draft` with "please provide school info" template
   - Call `state_set` with step="awaiting_school_info", waiting=true

**Step: awaiting_school_info** (user has replied with school info)
1. Extract: school full name (English) and school email domain from user's reply
2. If user provided personal email (Gmail, Yahoo, etc.) instead of school domain:
   - Call `front_create_draft` with "must use school email" template
   - Call `state_set` with step="awaiting_school_info", waiting=true
3. Determine school type:
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
1. User mentions they graduated or their school email is no longer accessible
2. Call `front_create_draft` with identity verification request template (need proof the original email was theirs)
3. Call `state_set` with step="awaiting_identity_verification", sub_type="email_expired_graduated", waiting=true

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
1. User mentions they want to cancel their education plan / subscription
2. Call `front_create_draft` with no-auto-renew explanation template
3. Call `state_set` with step="draft_created", sub_type="cancel_subscription"

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

Best regards,
Dify Support Team
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

Best regards,
Dify Support Team
```

### Must use school email
```
Dear [User's Name / Valued Customer],

Thank you for your reply!

Unfortunately, we're unable to process education plan applications using personal email addresses (such as Gmail or Yahoo). A school-issued email address with your institution's official domain is required for verification.

Could you please provide your school's official email domain instead?

Thank you for your understanding.

Best regards,
Dify Support Team
```

### Not eligible (K-12 or unaccredited)
⚠️ 需确认: 拒绝理由描述是否合适？
```
Dear [User's Name / Valued Customer],

Thank you for providing your school information.

After reviewing your application, we regret to inform you that [school name] does not currently qualify for Dify's Education Plan. Our education discount is available for higher education institutions (universities and colleges) that are accredited by government authorities.

We understand this may be disappointing, and we appreciate your interest in Dify. You're still welcome to use our free Sandbox plan, or explore our other pricing options at https://dify.ai/pricing.

Thank you for your understanding.

Best regards,
Dify Support Team
```

### Received, forwarding to team
```
Dear [User's Name / Valued Customer],

Thank you for providing your school information!

We've received your application and have forwarded it to our team for review. We'll get back to you once the verification is complete.


Best regards,
Dify Support Team
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

Best regards,
Dify Support Team
```

### Card binding cannot be bypassed
```
Dear [User Name / Valued Customer],

Thank you for reaching out and for sharing the screenshot.

At the moment, Education Plan activation requires completing the payment method / credit card binding step in the dashboard. We are not able to manually bypass this requirement or activate the Professional Education Plan directly from our side.

If you do not have a supported international credit card available, unfortunately you will not be able to complete the Education Plan activation at this time.

Thank you for your understanding.

Best regards,
Dify Support Team
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

Best regards,
Dify Support Team
```

### No-auto-renew explanation (for education plan cancel request)
```
Dear [User's Name / Valued Customer],

Thank you for reaching out regarding your education plan subscription.

We'd like to confirm that your Dify education plan will NOT automatically renew after its current term ends. There is no need to take any action to cancel — your subscription will simply expire at the end of the billing period without any further charges.

If you have any other questions, please don't hesitate to reach out.

Best regards,
Dify Support Team
```
