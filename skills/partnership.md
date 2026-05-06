# Skill: Partnership / Marketplace / Plugin

## Purpose
Handle partnership inquiries, marketplace cooperation, plugin cooperation, and plugin takedown requests.

## Steps

### All sub-types (plugin, marketplace, plugin_takedown)
1. Call `front_create_draft` with forwarding template
2. Call `front_forward_to_partnerships` with conversation_id and summary (1-2 sentence summary of the user's inquiry) — this creates a draft email to the partnerships team (赵晗青 + 赵雅雯) for Bobby to review before sending

## Reply Template

### Forwarding to partnerships team
```
Dear [User's Name / Valued Customer],

Thank you for reaching out to Dify!

We've forwarded your inquiry to our partnerships team, who will be in touch with you shortly.

Best regards,
Dify Support Team
```
