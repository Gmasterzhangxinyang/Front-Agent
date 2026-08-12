# Skill: Roadmap / Feature Requests

## Purpose
Handle questions about Dify's roadmap, upcoming features, and release timelines.


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
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps
1. Call `front_create_draft` with roadmap/feature request guidance for Bobby to review.
2. Call `state_set` with step="draft_created".
3. Do NOT send a direct reply and do NOT close automatically.
