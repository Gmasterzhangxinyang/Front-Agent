# Skill: Billing / Refund

## Purpose
Handle refund requests, duplicate charges, subscription changes, invoice issues, and other billing questions.

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
