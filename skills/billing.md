# Skill: Billing / Refund

## Purpose
Handle refund requests, duplicate charges, subscription changes, invoice issues, and other billing questions.

## Steps by Sub-type

### refund

**Step: initial**
1. Call `front_reply` with "please provide refund details" template
2. Call `state_set` with step="awaiting_refund_details", waiting=true

**Step: awaiting_refund_details** (user has provided details)
1. Extract from user's reply: account email, last charge date, charge reason, workspace ID
2. If workspace ID is missing: Call `front_reply` with "workspace ID instructions" template, keep state as awaiting_refund_details
3. If any other info is missing: Call `front_reply` asking for the missing fields
4. If all info present:
   - Call `front_assign` to assign conversation to 徐小茜 (teammate ID from config)
   - Call `front_add_comment` with summary: "退款请求 - 邮箱: [email], 扣款时间: [date], 原因: [reason], Workspace ID: [id]"
   - Call `front_reply` with "received, processing" template
   - Call `state_set` with step="assigned_to_xiaxi"

### duplicate_charge
1. Call `front_reply` with "please provide refund details" template (mention duplicate charge specifically)
2. Call `state_set` with step="awaiting_refund_details", sub_type="duplicate_charge", waiting=true
3. When details received: same as refund flow, but add "⚠️ 重复扣款" note in the comment to 徐小茜

### downgrade
1. Call `front_reply` with self-service downgrade template

### invoice
1. Call `front_reply` with invoice self-service template

### other
1. Call `linear_create_ticket` with conversation_id, title "Billing issue - [email]" and description
2. Use the URL returned from `linear_create_ticket` in the next step
3. Call `feishu_notify_bobby` with: "请转告张婉清处理账单问题。用户: [email]. Linear: [url from previous step]"
3. Call `front_reply` with "received, forwarding to team" template
4. Call `state_set` with step="ticket_created"

## Reply Templates

### Workspace ID instructions
```
Hi,

Thank you for the information provided.

To proceed further, please provide your Workspace ID by following the steps below:

1. Open your browser's developer tools (press F12)
2. Go to the Network tab and refresh the page
3. Look for a request named "current"
4. In that request's response, find the value associated with "id" — that is your Workspace ID
5. If you don't see the "current" request immediately, refresh the page and retry

Once you have it, please reply to this email with the Workspace ID so we can continue assisting you.

Thank you for your cooperation.

Best regards,
Dify Support Team
[AI generated]
```

### Request refund details
⚠️ 需确认: 所需信息字段是否完整？
```
Dear [User's Name / Valued Customer],

Thank you for reaching out regarding your refund request.

To process this for you, could you please provide the following information?

1. **Account email address** (the email associated with your Dify account)
2. **Date of last charge** (approximate date is fine)
3. **Reason for the charge** (e.g., Pro plan subscription, Team plan renewal)
4. **Workspace ID** (see instructions below if you're unsure how to find it)

To find your Workspace ID:
1. Open your browser's developer tools (press F12)
2. Go to the Network tab and refresh the page
3. Look for a request named "current"
4. In that request's response, find the value associated with "id" — that is your Workspace ID
5. If you don't see the "current" request immediately, refresh the page and retry

Once we have these details, we'll forward your request to our billing team right away.

Thank you for your patience!

Best regards,
Dify Support Team
[AI generated]
```

### Refund received, processing
⚠️ 需确认: 5-10工作日是否准确？
```
Dear [User's Name / Valued Customer],

Thank you for providing the details.

We've forwarded your refund request to our billing team for processing. If approved, the refund will be credited back to your original payment method within **5–10 business days**.

We'll notify you once the refund has been processed. If you have any questions in the meantime, please don't hesitate to reach out.

Best regards,
Dify Support Team
[AI generated]
```

### Downgrade / cancel self-service
⚠️ 需确认: 操作路径是否正确？
```
Dear [User's Name / Valued Customer],

Thank you for reaching out!

You can downgrade or cancel your subscription directly from your Dify dashboard:

**Bill → Manage Bill → Change Plan**

If you encounter any issues during the process, please reply and we'll be happy to assist.

Best regards,
Dify Support Team
[AI generated]
```

### Invoice self-service
⚠️ 需确认: 操作路径是否正确？
```
Dear [User's Name / Valued Customer],

Thank you for reaching out!

You can update your invoice details (including billing address) directly from your Dify dashboard:

**Bill → Manage Bill**

If you need further assistance, please don't hesitate to reply.

Best regards,
Dify Support Team
[AI generated]
```

### Billing issue forwarded to team
```
Dear [User's Name / Valued Customer],

Thank you for reaching out about your billing concern.

We've received your message and have forwarded it to our billing team for review. We'll follow up with you as soon as we have an update.

Thank you for your patience.

Best regards,
Dify Support Team
[AI generated]
```
