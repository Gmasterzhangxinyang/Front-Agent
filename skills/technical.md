# Skill: Technical / Bug Support

## Purpose
Handle technical questions, bug reports, API issues, service outages, and data privacy questions.

## Product Knowledge — Dify Version Overview

**Community Edition（社区版，免费开源）：**
- 免费、开源，可自部署
- 不支持多租户（不支持多 workspace）
- 不支持修改 Logo
- 只能企业内部使用，或通过 API 方式向外部提供服务
- 不可商用分发

**Premium（自部署商业版）：**
- 付费，自部署，需商业授权
- 支持修改 Logo
- 支持商用
- 不支持多租户
- 可通过 AWS Marketplace 或 https://dify.ai/pricing 购买

**SaaS 云端版本（Pro / Team）：**
- 云端托管，按月/年订阅
- 支持修改 Logo
- 不支持多租户
- 详见 https://dify.ai/pricing

**Enterprise（企业版）：**
- 支持多租户（多 workspace）
- 支持修改 Logo
- 支持商用及所有功能
- 包含其他版本所有功能
- 购买联系：business@dify.ai

## Steps by Sub-type

### Paid User (Team / Pro) — any technical sub_type except self_hosted and data_privacy
1. Call `front_create_draft` with the ticket system guidance template
2. Do NOT resolve — leave open for user to follow up if needed

### Free User (Sandbox) — how_to or workflow_issue
1. Call `docs_search` with keywords from the user's question to find relevant documentation
2. Call `github_search` with keywords from the user's issue to find related issues/PRs
3. Call `front_create_draft` with documentation guidance + upgrade suggestion, referencing docs and any relevant GitHub issues found

### Free User — feasibility (evaluating before purchase)
1. Call `docs_search` to check if the feature exists in official documentation
2. Call `github_search` to check if the feature is planned or discussed
3. Call `front_create_draft` answering ONLY what you are 100% certain Dify can do based on official docs
4. Do NOT make promises about features you are unsure of
5. Include pricing page link to encourage upgrade

### Free User — bug_report
1. Call `github_search` to check if this bug is already reported or fixed
2. Call `front_create_draft` directing to GitHub issues, mentioning any related issue found

### Free User — api_issue
1. Call `github_search` to check for known API issues
2. Call `front_create_draft` directing to pricing page for API limits info and docs for API key management

### Premium User (self-hosted licensed) — any sub_type
1. Call `docs_search` with keywords from the user's issue to find relevant documentation
2. Call `github_search` with keywords from the user's issue
3. Call `front_create_draft` with a helpful answer based on official docs and GitHub findings
4. If issue is complex and cannot be resolved by AI, call `feishu_notify_bobby` with summary
5. Leave conversation open

### Self-hosted Community Edition (non-Premium) — any sub_type
1. Call `docs_search` to find relevant documentation
2. Call `github_search` to check for known issues or workarounds
3. Call `front_create_draft` directing to docs and GitHub community, referencing relevant docs and issues found
   - If the user asks about multi-tenancy, logo customization, or commercial use: clarify that Community Edition does NOT support these — they need Premium (self-hosted with commercial license) or Enterprise Edition

### Outage (any user)
1. Call `front_create_draft` acknowledging the issue
2. Call `linear_create_ticket` with title "Service outage report - [sender email]" and description
3. Call `feishu_notify_bobby` with summary
4. Leave conversation open

### Data Privacy — general question
1. Call `front_create_draft` clearly stating Dify does NOT use user data for training and does NOT share data

### Data Privacy — serious concern (potential data breach)
1. Route to security skill instead

## Reply Templates

### Paid user → ticket system
```
Dear [User's Name / Valued Customer],

Thank you for reaching out to Dify Support.

We're sorry to hear you're experiencing this issue. As a Pro/Team subscriber, you have access to our priority technical support.

Please submit your request directly through your dashboard:
Settings → Support → Contact Us

When submitting, please do not remove the subscription verification details at the bottom of your email — they help us verify your account status and prioritize your request.

We'll get back to you as soon as possible through the ticket system.

Best regards,
Dify Support Team
[AI generated]
```

### Free user → docs + upgrade
```
Dear [User's Name / Valued Customer],

Thank you for reaching out to Dify Support. We're happy to help!

[Insert relevant guidance based on the user's specific question, referencing https://docs.dify.ai]

Please note that priority technical support via our ticket system is available for Pro and Team plan subscribers. For free tier users, we recommend:
- Our documentation: https://docs.dify.ai
- GitHub issues for bug reports: https://github.com/langgenius/dify/issues

If you'd like access to priority support, you can upgrade your plan at: https://dify.ai/pricing

We hope this helps! Feel free to reply if you have further questions.

Best regards,
Dify Support Team
[AI generated]
```

### Feasibility inquiry
```
Dear [User's Name / Valued Customer],

Thank you for your interest in Dify!

[Answer only what you are 100% certain about based on official documentation. Do not speculate.]

For a full overview of Dify's capabilities and pricing plans, please visit:
- Documentation: https://docs.dify.ai
- Pricing: https://dify.ai/pricing

If you're interested in an Enterprise plan, please reach out to business@dify.ai with your company name, size, and use case.

Best regards,
Dify Support Team
[AI generated]
```

### Data privacy
```
Dear [User's Name / Valued Customer],

Thank you for your question regarding data privacy.

We want to assure you that Dify does not use your data for model training, and we do not share your data with third parties. Your data remains private and secure.

For more details on our privacy practices, please refer to our Privacy Policy.

Best regards,
Dify Support Team
[AI generated]
```

### Outage acknowledgment
```
Dear [User's Name / Valued Customer],

Thank you for letting us know. We're sorry to hear you're experiencing access issues.

Our team has been notified and is looking into this. We'll follow up as soon as we have more information.

We apologize for any inconvenience this may cause.

Best regards,
Dify Support Team
[AI generated]
```
