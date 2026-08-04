# Skill: Purchase / Pricing Inquiries

## Purpose
Handle questions about purchasing Dify plans, pricing, and reseller/agent inquiries.

## Product Knowledge — Dify Plans and Features

### Community Edition (Self-hosted, Free, Open-source)
- **Multi-tenancy**: ❌ NOT supported
- **Logo customization**: ❌ NOT supported
- **Commercial use**: ⚠️ Only for internal use within your organization, OR providing services to external users via API. NOT for commercial redistribution.
- **Support**: Community support via GitHub and docs

### Premium (AWS deployment for POC)
- **Foundation**: A commercial deployment option based on Dify Community Edition
- **Primary fit**: Teams that want to deploy Dify quickly in AWS with a one-click setup for a proof of concept (POC)
- **Production guidance**: Recommend Dify Enterprise when the use case involves a large-scale production environment, high concurrency, multiple teams, enterprise-grade security management, access control, or stronger stability requirements
- **Purchase**: Available on AWS Marketplace or via https://dify.ai/pricing

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


## Draft Quality Bar
- Write concise, professional English unless the user wrote primarily in another language.
- Answer only what the email supports. Do not invent product behavior, policy exceptions, timelines, refunds, eligibility, or engineering commitments.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an issue is fixed, approved, refunded, or escalated unless a tool result or policy explicitly proves it.
- End with a clear next step for the user or a clear expectation that the team will review.

## Steps by Sub-type

### enterprise
1. Call `front_create_draft` with enterprise inquiry template

### premium
1. Call `front_create_draft` with the Premium introduction template.
2. After the draft is created, call `state_set` with category="purchase", sub_type="premium", step="draft_created", and waiting=false.
3. Match the customer's primary language and faithfully preserve the distinction between Premium for AWS POC use and Enterprise for demanding production use.
4. If the customer wants to learn more about Enterprise:
   - For a clearly Japanese customer, ask whether they consent to having their inquiry shared with and being connected to the Japan sales team. Do not say that it has already been forwarded.
   - Otherwise, ask for their country or region so the appropriate sales team can be identified.
5. Keep the conversation open for human review. Do not forward the conversation to a sales team before the customer provides the requested location or consent.

### pro_team
1. Call `front_create_draft` with pricing guidance template

### promo_code
1. Call `front_create_draft` with no promo code template

### reseller
1. Do NOT create a customer draft.
2. Call `front_forward_to_partnerships` with conversation_id and summary (1-2 sentence summary of the user's inquiry). This forwards the original thread to `marketing@dify.ai`.
3. Call `state_set` with step="forwarded_keep_open", sub_type="reseller".

## Reply Templates

### Premium introduction
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify Premium.

Dify Premium is a commercial deployment option based on Dify Community Edition. It is primarily designed for teams that want to deploy Dify quickly in AWS with a one-click setup for a proof of concept (POC).

If your use case involves a large-scale production environment, high-concurrency access, collaboration across multiple teams, enterprise-grade security management, access control, or stronger stability requirements, we recommend Dify Enterprise. Enterprise is better suited to organizations with greater requirements for scalability, administration, security, and production stability.

If you would like to learn more about Dify Enterprise, please let us know your country or region, and we can help connect you with the appropriate sales team.

Best regards,
Dify Support Team
```

Chinese-language reference:
```
您好，

感谢您对 Dify Premium 的关注。

Dify Premium 是基于 Dify Community Edition 的商业化部署选项，主要面向希望快速在 AWS 中一键部署 Dify 用作 POC 的场景。

如果您的使用场景涉及大规模生产环境、高并发访问、多团队协作、企业级安全管理、权限控制或对稳定性有较高要求，我们建议选用 Dify Enterprise。Enterprise 更适合对扩展能力、管理能力、安全性以及生产环境稳定性有较高要求的场景及企业客户。

如果您希望进一步了解 Dify Enterprise 方案，请告知您所在的国家或地区，我们可以协助对接对应的销售团队。

谢谢。
```

For a clearly Japanese customer, replace the final country/region paragraph with a consent question in the customer's language equivalent to:

```
If you would like to learn more about Dify Enterprise, would you be comfortable with us sharing your inquiry with and connecting you to our Japan sales team?
```

Do not infer that someone is a Japanese customer from a personal name alone. Treat the customer as clearly Japanese only when the message or account context provides a strong signal, such as an explicit Japan location, a Japanese company/address, a Japanese-language inquiry, or a `.jp` organization domain.

### Premium custom multi-AZ / Active-Active architecture
If the customer explicitly proposes a dual-AZ or multi-AZ Active-Active Premium deployment, typically behind a load balancer and with shared services such as S3, RDS/PostgreSQL, or ElastiCache/Redis, add the approved architecture paragraph from `technical.md` in the customer's language before recommending Enterprise. Explain that the custom topology differs from the standard one-click Premium deployment on AWS Marketplace, its engineering complexity and possible implementation issues cannot be predicted, and the approach is therefore not recommended. Do not provide configuration steps or make additional licensing/support promises.

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

We've received your inquiry and have forwarded it to the appropriate team for review. A team member will be in touch with you shortly.

If you have any immediate questions in the meantime, feel free to reply.

Best regards,
Dify Support Team
```
