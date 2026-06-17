# Skill: Data Export Request

## Purpose
Handle requests from users who want to export or download their personal data.

## Steps
1. Call `front_create_draft` with data export guidance for Bobby to review.
2. Call `state_set` with step="draft_created".
3. Do NOT send a direct reply and do NOT close automatically.
