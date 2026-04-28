# Skill: Education Plan

## Purpose
Handle education plan applications, rejections, and discount issues.

## Key Facts
- Education discount: 100% off, valid for 1 year
- After 1 year, user can reapply
- Only higher education institutions (universities, colleges, government-accredited) qualify
- K-12 schools and unaccredited institutions do NOT qualify
- Must use school email domain (not personal email like Gmail)

## Steps by Sub-type

### rejected (education plan application rejected)

**Step: initial**
1. Call `front_reply` with "please provide school info" template
2. Call `state_set` with step="awaiting_school_info", waiting=true

**Step: awaiting_school_info** (user has replied with school info)
1. Extract: school full name (English) and school email domain from user's reply
2. If user provided personal email (Gmail, Yahoo, etc.) instead of school domain:
   - Call `front_reply` with "must use school email" template
   - Keep state as awaiting_school_info
3. Determine school type:
   - **Higher education (university/college, government-accredited):**
     - Call `linear_create_ticket` with conversation_id, title "Education plan application - [school name]" and description: school full name (English), email domain, AI assessment result
     - Use the URL returned from `linear_create_ticket` in the next step
     - Call `feishu_notify_bobby` with: "请转告张婉清审核教育版申请。学校: [school name], 域名: [domain]. Linear: [url from previous step]"
     - Call `front_reply` with "received, forwarding to team" template
     - Call `state_set` with step="ticket_created"
   - **K-12 or unaccredited:**
     - Call `front_reply` with "not eligible" template

### no_discount (edu verified but discount not showing)

**Step: initial**
1. Check if user mentions they can see the "edu" badge in their account
2. If they see the edu badge but no discount:
   - Call `front_reply` with billing guidance template
3. If they don't see the edu badge (not verified):
   - Call `front_reply` with "please provide school info" template
   - Call `state_set` with step="awaiting_school_info", waiting=true
   - Continue with the same logic as `rejected` flow: assess school type, create ticket if eligible, reject if not

## Reply Templates

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
[AI generated]
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
[AI generated]
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
[AI generated]
```

### Received, forwarding to team
```
Dear [User's Name / Valued Customer],

Thank you for providing your school information!

We've received your application and have forwarded it to our team for review. We'll get back to you once the verification is complete.

This typically takes 1–3 business days.

Best regards,
Dify Support Team
[AI generated]
```

### Billing guidance (edu badge visible but no discount)
⚠️ 需确认: 操作路径是否正确？
```
Dear [User's Name / Valued Customer],

Thank you for reaching out!

To apply your education discount, please follow these steps:

1. Go to **Bill** in your Dify dashboard
2. Select the **Pro** plan
3. Choose **annual billing** (yearly)
4. The 100% education discount coupon should appear automatically

Please note that the discount only applies to the Pro plan with annual billing. If you've selected monthly billing, the discount will not show.

If you've followed these steps and still don't see the discount, please reply and let us know — we'll be happy to investigate further.

Best regards,
Dify Support Team
[AI generated]
```
