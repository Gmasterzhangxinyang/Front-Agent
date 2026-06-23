# Skill: Business / Enterprise Inquiries

## Purpose
Handle enterprise sales, procurement, demo, quote, and business-plan inquiries.

## Detection
Emails should be classified as `business` when they contain:
- Enterprise plan inquiries
- Sales/pricing questions for teams/companies
- Requests for demos, quotes, or sales meetings
- Vendor registration or procurement processes
- Self-hosted enterprise licensing

## Steps

### business (Enterprise/Business inquiries)

Business is normally handled before the LLM skill loop by deterministic routing:
1. `agent/routing.py` chooses `business_move_inbox`.
2. `front_forward_to_business` moves the conversation to the configured Business inbox.
3. `state_set` records step="moved_inbox".
4. No customer draft, no direct reply, and no auto-close.

If this skill is reached unexpectedly, do not create a customer draft. Call `front_forward_to_business` with conversation_id and a concise summary, then call `state_set` with step="moved_inbox".
