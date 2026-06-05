# Skill: Business / Enterprise Inquiries

## Purpose
Detect business/enterprise related inquiries and route them to the Business inbox. No agent processing needed.

## Detection
Emails should be classified as `business` when they contain:
- Enterprise plan inquiries
- Sales/pricing questions for teams/companies
- Business development/partnerships (non-technical)
- Requests for demos, quotes, or sales meetings
- References to "enterprise", "business plan", "team plan" in context of buying
- Self-hosted enterprise licensing
- Vendor registration or procurement processes

## Steps

### business (Enterprise/Business inquiries)

**Step: initial**
1. Call `move_conversation_to_inbox` with target inbox "Business" to route the conversation to the Business team
2. Do NOT reply to the user
3. Do NOT create any drafts
4. Call `state_set` with step="done" to mark as handled

**Important**: This category requires no further agent action after routing.