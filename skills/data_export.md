# Skill: Data Export Request

## Purpose
Handle requests from users who want to export or download their personal data.


## Draft Quality Bar
- Write concise, professional English unless the user wrote primarily in another language.
- Answer only what the email supports. Do not invent product behavior, policy exceptions, timelines, refunds, eligibility, or engineering commitments.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an issue is fixed, approved, refunded, or escalated unless a tool result or policy explicitly proves it.
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps
1. Call `front_create_draft` with data export guidance for Bobby to review.
2. Call `state_set` with step="draft_created".
3. Do NOT send a direct reply and do NOT close automatically.
