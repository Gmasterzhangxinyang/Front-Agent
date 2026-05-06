# Skill: Purchase / Pricing Inquiries

## Purpose
Handle questions about purchasing Dify plans, pricing, and reseller/agent inquiries.

## Steps by Sub-type

### enterprise
1. Call `front_create_draft` with enterprise inquiry template

### pro_team
1. Call `front_create_draft` with pricing guidance template

### reseller
1. Call `front_create_draft` with "forwarding to partnerships team" template
2. Call `front_forward` to 赵晗青's email with cc to 赵雅雯

## Reply Templates

### Enterprise inquiry
⚠️ 需确认: business@dify.ai 是否正确？
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify's Enterprise plan!

For Enterprise plan inquiries, please reach out directly to our business team at business@dify.ai. Please include your company name, company size, and a brief description of your use case so we can assist you more effectively.

For verification purposes, we recommend using your corporate email address when making business inquiries.

We look forward to hearing from you!

Best regards,
Dify Support Team
[AI generated]
```

### Pro/Team pricing
⚠️ 需确认: pricing页面链接是否正确？
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify's paid plans!

You can find a full comparison of our Pro, Team, and other plans on our pricing page:
👉 https://dify.ai/pricing

Here's a quick overview:
- **Sandbox (Free)**: Great for getting started and exploring Dify's features
- **Pro**: Ideal for individual professionals and small teams
- **Team**: Best for growing teams that need collaboration features
- **Premium**: For organizations that need self-hosted deployment with a commercial license

If you have specific questions about which plan is right for you, feel free to reply and we'll be happy to help!

Best regards,
Dify Support Team
[AI generated]
```

### Reseller inquiry
```
Dear [User's Name / Valued Customer],

Thank you for your interest in partnering with Dify!

We've forwarded your inquiry to our partnerships team, who will be in touch with you shortly.

Best regards,
Dify Support Team
[AI generated]
```
