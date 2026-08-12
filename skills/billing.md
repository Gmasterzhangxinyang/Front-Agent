# Skill: Billing / Refund

## Purpose
Handle refund requests, duplicate charges, subscription changes, invoice issues, and other billing questions.


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
- When a self-service path exists, give the exact navigation labels and location. Do not replace a known self-service path with vague wording such as "our team can review", "we'll assist", or "contact support if you have trouble".
- End with a clear next step for the user.

## Steps by Sub-type

### refund / duplicate_charge
1. Call `front_create_draft` with guidance asking the user to submit through the proper billing/support path and include charge details.
2. Call `state_set` with step="draft_created".
3. Do NOT close automatically.

### downgrade / paid subscription cancellation
Use this branch when a Dify Cloud paid-plan customer wants to downgrade, stop renewal, or cancel the subscription. This is a self-service flow; do not offer manual cancellation or say that the team will review it.

1. Call `front_create_draft` with concise instructions using the most specific route supported by the conversation:
   - If the customer replied to a Stripe renewal reminder, make that the primary route: in the renewal reminder email, scroll to the bottom of the subscription card and click **Manage your subscriptions**, located directly below the blue **Update payment method** button. In the Stripe billing portal, select the active Dify subscription, click **Cancel plan**, and confirm the cancellation.
   - Also give the Dify Cloud route when helpful: click the current workspace name in the upper-left corner -> **Settings** -> **Billing** -> the **Billing and Subscriptions** card -> **Manage**. In the Stripe billing portal, select the active Dify subscription, click **Cancel plan**, and confirm.
   - If the conversation includes a renewal date, tell the customer to complete the cancellation before that exact date to prevent renewal.
   - Do not claim the subscription was already canceled. Do not claim cancellation immediately deletes the workspace or terminates access.
   - Do not add a fallback asking the customer to provide an account/workspace email for manual review.
2. Call `state_set` with step="draft_created", sub_type="downgrade", waiting=false.

Approved example for a customer who replied to a renewal reminder:

```text
Hi,

To cancel your Dify Professional subscription before <renewal date>, please open the renewal reminder email you replied to. At the bottom of the subscription card, directly below the blue "Update payment method" button, click "Manage your subscriptions."

In the Stripe billing portal, select your active Dify subscription, click "Cancel plan," and confirm the cancellation.

You can also reach the same portal from Dify Cloud: click your current workspace name in the upper-left corner, then go to Settings -> Billing -> Billing and Subscriptions -> Manage.

```

### invoice
Use the existing-invoice flow below only when the user asks to correct or reissue an invoice that has already been issued. For ordinary invoice downloads or future billing-detail updates, create the normal billing-portal self-service draft and set step="draft_created".

#### Mainland China tax invoice / VAT fapiao
When the customer asks for a Mainland China tax invoice (fapiao), including a VAT special or general invoice:

1. Describe LangGenius, Inc.'s actual invoicing capability. Do not make broader tax-law conclusions or use entity location/status as a simplified legal cause.
2. State that the existing invoice and receipt are the official commercial billing documents available for the transaction. Do not tell the customer to use them for reimbursement or imply that the institution will accept them.
3. Explicitly leave acceptance to the institution's reimbursement policies.
4. Always offer a bounded next step: ask the customer to share the institution's specific additional billing-information or supporting-document requirements so the team can check what it is able to provide. Do not promise that another document can or will be issued.
5. Use the following authoritative English wording. If the customer's current request is primarily non-English, preserve this English version first and append the required reference notice and a faithful matching-language translation:

```text
Hi <name>,

Thank you for reaching out and for providing the payment details.

LangGenius, Inc. is not a PRC-registered invoicing entity and does not issue invoices through the PRC tax administration system. Therefore, we're unable to provide a Chinese VAT invoice, including either a special VAT invoice or a general VAT invoice.

The invoice and receipt you have already received are the official commercial billing documents issued by LangGenius, Inc. for this transaction. Whether these documents can be accepted for reimbursement is subject to your institution's reimbursement policies.

If your institution requires additional billing information or supporting documentation, please share the specific requirements and we can check what we're able to provide.

```

Do not use the former wording `LangGenius is a non-PRC entity, therefore...`, `For reimbursement purposes, please use...`, or any equivalent tax-law inference or reimbursement instruction. Do not suggest that downloading an Invoice/receipt or updating the Billing Portal can produce a PRC tax invoice. If the request also concerns correction or reissuance of an already-issued commercial Invoice, continue with the existing-invoice guidance below.

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
