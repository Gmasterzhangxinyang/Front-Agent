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
2. Call `front_forward_to_partnerships` with conversation_id — this automatically forwards to the partnerships team (赵晗青 + 赵雅雯) using system-configured email addresses

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

Here's a quick overview:

**SaaS Plans (Cloud-hosted by Dify):**
- **Sandbox (Free)**: Great for getting started and exploring Dify's features
- **Pro**: Ideal for individual professionals and small teams
- **Team**: Best for growing teams that need collaboration features
- All SaaS plans support logo customization

**Self-hosted Plans:**
- **Community Edition (Free, open-source)**: For internal use within your own organization, or providing services to external users via API. Does NOT support multi-tenancy or logo modification. Not for commercial redistribution.
- **Premium (Self-hosted, commercial license)**: Supports logo customization and commercial use. The pricing page (https://dify.ai/pricing) gives a general overview — for detailed pricing and purchase, refer users to AWS Marketplace as the primary channel

**Enterprise Plan:**
- Supports multi-tenancy (multiple workspaces), logo customization, commercial use, and all features from other plans
- For Enterprise inquiries, please contact: business@dify.ai

If you have specific questions about which plan is right for you, feel free to reply and we'll be happy to help!

Best regards,
Dify Support Team
```

### No promo code available
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify!

We appreciate your inquiry about promotional codes. At this time, we do not have any active promo codes or seasonal discounts available.

However, we do offer:
- **Free Sandbox plan**: Full access to explore Dify's features at no cost
- **Education discount**: 100% off for verified students and educators at accredited higher education institutions
- **Transparent pricing**: You can view our current pricing at https://dify.ai/pricing

If you're interested in our Enterprise plan for larger organizations, please reach out to business@dify.ai to discuss custom pricing options.

We hope you'll give Dify a try!

Best regards,
Dify Support Team
```

### Reseller inquiry
```
Dear [User's Name / Valued Customer],

Thank you for your interest in partnering with Dify!

We've forwarded your inquiry to our partnerships team, who will be in touch with you shortly.

Best regards,
Dify Support Team
```
