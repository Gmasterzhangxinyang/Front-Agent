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
1. Call `front_create_draft` with invoice self-service template.
2. Call `state_set` with step="draft_created".

### other
1. Call `front_create_draft` with "received, forwarding to team" template.
2. Call `state_set` with step="draft_created".

## Important Rules
- Default customer action is draft, not direct reply.
- Keep the conversation open after creating a draft.
