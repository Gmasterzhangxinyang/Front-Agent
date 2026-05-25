# Skill: Purchase / Pricing Inquiries

## Purpose
Handle questions about purchasing Dify plans, pricing, and reseller/agent inquiries.

## Product Knowledge — Dify Plans and Features

### Community Edition (Self-hosted, Free, Open-source)
- **Multi-tenancy**: ❌ NOT supported
- **Logo customization**: ❌ NOT supported
- **Commercial use**: ⚠️ Only for internal use within your organization, OR providing services to external users via API. NOT for commercial redistribution.
- **Support**: Community support via GitHub and docs

### Premium (Self-hosted, Commercial License)
- **Multi-tenancy**: ❌ NOT supported
- **Logo customization**: ✅ Supported
- **Commercial use**: ✅ Supported (commercial redistribution allowed)
- **Purchase**: Available on AWS Marketplace or via https://dify.ai/pricing
- **Support**: Standard support

### SaaS Plans (Cloud-hosted by Dify)
- **Sandbox (Free)**: For getting started and exploring
- **Pro**: For individual professionals and small teams
- **Team**: For growing teams with collaboration needs
- **Logo customization**: ✅ All SaaS plans support logo customization
- **Multi-tenancy**: ❌ NOT supported (single workspace per account)

### Enterprise Plan
- **Multi-tenancy**: ✅ Supported (multiple workspaces)
- **Logo customization**: ✅ Supported
- **Commercial use**: ✅ Supported
- **All features**: Includes all features from other plans
- **Support**: Dedicated support with SLA
- **Contact**: business@dify.ai

## Steps by Sub-type

### enterprise
1. Call `front_create_draft` with enterprise inquiry template

### pro_team
1. Call `front_create_draft` with pricing guidance template

### promo_code
1. Call `front_create_draft` with no promo code template

### reseller
1. Call `front_create_draft` with "forwarding to partnerships team" template
2. Call `front_forward_to_partnerships` with conversation_id and summary (1-2 sentence summary of the user's inquiry)

## Reply Templates

### Enterprise inquiry
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify's Enterprise plan!

The Enterprise plan is our most comprehensive offering, supporting:
- Multi-tenancy (multiple workspaces)
- Logo customization
- Commercial use and redistribution
- All features from other Dify plans
- Dedicated support and SLA

For Enterprise plan inquiries, please reach out directly to our business team at business@dify.ai. Please include your company name, company size, and a brief description of your use case so we can assist you more effectively.

For verification purposes, we recommend using your corporate email address when making business inquiries.

We look forward to hearing from you!

Best regards,
Dify Support Team
```

### Pro/Team pricing
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify's paid plans!

You can find a full comparison of our plans on our pricing page:
👉 https://dify.ai/pricing

If you have specific questions about which plan might suit your needs best, feel free to reply and let us know a bit more about your use case — we'll be happy to advise.

Best regards,
Dify Support Team
```

### No promo code available
```
Dear [User's Name / Valued Customer],

Thank you for reaching out!

At this time, we don't have promotional codes available for Dify plans. However, we do offer the following options:

- **Free Sandbox plan**: You can explore Dify at no cost to get started
- **Education discount**: If you're affiliated with a higher education institution, you may qualify for a 100% discount on the Pro plan — learn more and apply at https://dify.ai/pricing#education

For other discount programs or special offers, please feel free to reply and we'll see what we can do.

Best regards,
Dify Support Team
```

### Reseller / agent inquiry
```
Dear [User's Name / Valued Customer],

Thank you for reaching out about partnership or reseller opportunities with Dify!

We've received your inquiry and have forwarded it to our partnerships team for review. A team member will be in touch with you shortly.

If you have any immediate questions in the meantime, feel free to reply.

Best regards,
Dify Support Team
```
