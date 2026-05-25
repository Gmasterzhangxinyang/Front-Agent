# Skill: Security

## Purpose
Handle security-related reports and concerns.

## Steps by Sub-type

### general (non-urgent security concern)
1. Call `front_add_tag` with conversation_id and tag_id "tag_5fgwpn" (security_from_hello)
2. Leave conversation open — Front rule will route it to security inbox based on the tag

### urgent (active breach, data leak, critical vulnerability)
1. Call `front_add_tag` with conversation_id and tag_id "tag_5fgwpn" (security_from_hello)
2. Leave conversation open — Front rule will route it to security inbox based on the tag

## Important
- Do NOT create any draft or reply
- Do NOT notify Bobby
- Just add the tag and leave it — routing is handled automatically by Front rules
