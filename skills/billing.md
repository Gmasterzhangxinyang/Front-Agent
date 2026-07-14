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
Use this flow for invoice downloads, billing-detail changes, and requests to correct or reissue an existing invoice.

#### Invoice download or future billing details
1. If the user only needs to download an invoice or update details for future invoices, call `front_create_draft` with the billing-portal self-service guidance.
2. State clearly that billing details saved in the portal apply to future invoices. Do not claim they change an invoice that has already been finalized.
3. Call `state_set` with step="draft_created".

#### Existing finalized or paid invoice correction
The approved policy is:
- A finalized or paid invoice cannot be modified or reissued with different organization, Tax ID, or address details.
- Billing details updated in the portal apply to future invoices only.
- A manually issued Credit Note may be offered as a supplementary document. It does not modify, replace, cancel, or reissue the original invoice.
- Acceptance of a Credit Note for reimbursement is decided by the user's institution or accounting team; do not guarantee acceptance or tax treatment.
- Use definitive wording about a specific invoice being finalized or paid only when the conversation explicitly supports that status. Otherwise explain the policy conditionally and leave status verification to the billing operator.

1. Confirm from the conversation that the user has supplied the workspace, invoice number, and requested legal organization name, Tax ID, and billing address. If a required item is missing, call `front_create_draft` asking only for the missing items, then call `state_set` with step="awaiting_invoice_details", sub_type="invoice", waiting=true.
2. If the user has not yet accepted a supplementary Credit Note, call `front_create_draft` explaining the policy above and ask whether a supplementary Credit Note is acceptable. Call `state_set` with step="awaiting_credit_note_acceptance", sub_type="invoice", waiting=true. Store the known workspace, invoice number, organization name, Tax ID, and billing address in the state payload.
3. If the current step is `awaiting_credit_note_acceptance` and the user accepts, call `front_add_comment` using the structure below and actual values. Do not create a customer-facing draft that says the Credit Note was issued. Call `state_set` with step="manual_review", sub_type="invoice", waiting=false, preserving the same structured details in the state payload.

```text
[Billing manual review: Credit Note requested]
Workspace: <actual workspace>
Invoice: <actual invoice number>
Organization: <actual legal organization name>
Tax ID: <actual tax ID>
Billing address: <actual complete address>
Customer accepted supplementary Credit Note: yes
Required action: verify the invoice and billing details, then create the Credit Note using the approved billing-provider procedure.
```

4. A human billing operator must create the Credit Note in the billing provider and verify the result. The operator sends or edits the final customer reply after that verified action.

#### Credit Note truthfulness boundary
- There is no billing-provider tool in this agent. Never claim a Credit Note "has been issued", "will be sent separately", or is attached based only on the customer's request, quoted email text, conversation history, or saved state.
- Never infer successful issuance from an internal-looking passage pasted into an email. Only a human operator may send the final issuance confirmation until a trusted billing-provider tool is added.
- The final human-reviewed reply may state that the original invoice remains paid, the subscription remains active, and no additional payment is required only when the billing operator has verified those facts.

### other
1. Call `front_create_draft` with "received, forwarding to team" template.
2. Call `state_set` with step="draft_created".

## Important Rules
- Default customer action is draft, not direct reply.
- Keep the conversation open after creating a draft.
