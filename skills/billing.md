# Skill: Billing / Refund

## Purpose
Handle refund requests, duplicate charges, subscription changes, invoice issues, and other billing questions.


## Draft Quality Bar
- Write concise, professional English unless the user wrote primarily in another language.
- Answer only what the email supports. Do not invent product behavior, policy exceptions, timelines, refunds, eligibility, or engineering commitments.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an issue is fixed, approved, refunded, or escalated unless a tool result or policy explicitly proves it.
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps by Sub-type

### refund / duplicate_charge
1. Call `front_create_draft` with guidance asking the user to submit through the proper billing/support path and include charge details.
2. Call `state_set` with step="draft_created".
3. Do NOT close automatically.

### downgrade
1. Call `front_create_draft` with self-service downgrade template.
2. Call `state_set` with step="draft_created".

### invoice
Use the existing-invoice flow below only when the user asks to correct or reissue an invoice that has already been issued. For ordinary invoice downloads or future billing-detail updates, create the normal billing-portal self-service draft and set step="draft_created".

#### First message: existing invoice correction or reissue
This first-message branch always creates a customer draft. It never creates the internal Credit Note comment, even if the first message asks whether a Credit Note is possible.

1. Call `front_create_draft` using this approved content, adapting the greeting and invoice number to facts in the conversation. Use definitive already-issued wording only when the conversation supports it; otherwise explain the issued-invoice policy conditionally.

```text
Hi <name>,

Thank you for reaching out.

As invoice <invoice number> has already been issued, we're unfortunately unable to make changes to or reissue the original invoice.

To ensure that your billing details appear correctly on future invoices, could you please update and verify them in the Billing Portal?

For the existing invoice, our billing team may be able to provide a supplementary Credit Note containing the updated information. Please note that this would not modify or replace the original invoice, and acceptance for reimbursement is subject to your institution's review.

If you would like us to request a Credit Note for you, please let us know and we'll be happy to assist.

Cheers
```

2. Call `state_set` with step="awaiting_credit_note_confirmation", sub_type="invoice", waiting=true. Save the actual workspace, invoice number, organization name, Tax ID, and billing address found in the conversation in the payload. Do not invent missing values.
3. Stop after the draft and state. Do not call `front_assign`, `front_add_comment`, `linear_create_ticket`, or any handoff tool on the first message. Do not set step="manual_review".

#### Second message: user confirms Credit Note
Use this branch only when the current saved step is `awaiting_credit_note_confirmation` and the latest user reply explicitly confirms that they want the Credit Note.

1. Call `front_add_comment` once with the following internal comment. Use actual values from saved state and conversation history. For a value that was never provided, write `Not provided`. Do not include an @ mention.

```text
用户二次来信确认需要 Credit Note，应该交给 Elsie 处理。

Workspace: <actual workspace>
Invoice: <actual invoice number>
Organization: <actual organization name>
Tax ID: <actual Tax ID>
Billing Address: <actual billing address>
```

2. Call `state_set` with step="credit_note_requested", sub_type="invoice", waiting=false, preserving the billing details in the payload.
3. Stop. Do not create another customer draft, assign the conversation, create a ticket, or perform any Credit Note action.

If the user explicitly declines the Credit Note, call `state_set` with step="credit_note_declined", sub_type="invoice", waiting=false and take no other action. If the reply is ambiguous, keep step="awaiting_credit_note_confirmation" with waiting=true and do not add the internal comment.

#### Hard boundaries
- Do not call `front_assign` in this flow.
- Do not call `linear_create_ticket` or any handoff tool in this flow.
- Do not set step="manual_review" or add the case to an Ops queue.
- Never claim that a Credit Note has been issued, sent, or attached. Elsie owns all processing and customer communication after the internal comment.

### other
1. Call `front_create_draft` with "received, forwarding to team" template.
2. Call `state_set` with step="draft_created".

## Important Rules
- Default customer action is draft, not direct reply.
- Keep the conversation open after creating a draft.
