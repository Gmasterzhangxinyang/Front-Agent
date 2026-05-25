# Skill: Billing / Refund

## Purpose
Handle refund requests, duplicate charges, subscription changes, invoice issues, and other billing questions.

## Steps by Sub-type

### refund / duplicate_charge
1. Call `front_reply_with_template` — sends the X template directing user to submit a support ticket
2. Call `front_close_conversation`

### downgrade
1. Call `front_create_draft` with self-service downgrade template

### invoice
1. Call `front_create_draft` with invoice self-service template

### other
1. Call `front_create_draft` with "received, forwarding to team" template

## Reply Templates

### Downgrade / cancel self-service
```
Dear Valued Customer,

Thank you for reaching out!

You can downgrade or cancel your subscription directly from your Dify dashboard:

**Bill → Manage Bill → Change Plan**

If you encounter any issues during the process, please reply and we'll be happy to assist.

Best regards,
Dify Support Team
```

### Invoice self-service
```
Dear Valued Customer,

Thank you for reaching out!

You can update your invoice details (including billing address) directly from your Dify dashboard:

**Bill → Manage Bill**

If you need further assistance, please don't hesitate to reply.

Best regards,
Dify Support Team
```

### Billing issue forwarded to team
```
Dear Valued Customer,

Thank you for reaching out about your billing concern.

We've received your message and have forwarded it to our billing team for review. We'll follow up with you as soon as we have an update.

Thank you for your patience.

Best regards,
Dify Support Team
```
