# Skill: Technical Support

## Purpose
Handle technical issues: workflow problems, bug reports, how-to questions, feasibility inquiries, API issues, outages, data privacy, and self-hosted configuration.

## Steps

### 1. Analyze the technical issue
Determine the sub_type:
- **workflow_issue**: Workflow not working, step failing
- **bug_report**: Something broken, unexpected behavior
- **how_to**: How to do X, how to configure Y
- **feasibility**: Can Dify do X? Evaluating before purchase
- **api_issue**: API limits, API key, API usage
- **outage**: Service down, can't access Dify at all
- **data_privacy**: Questions about data storage, training, GDPR
- **self_hosted**: Self-hosted installation/config (non-Premium)

### 2. Reply using X template
For ALL technical inquiries, call `front_reply_with_template` to reply using the X template:

**X Template Content:**
```
Dear Valued Customer,

Thank you for your inquiry. We appreciate your interest in Dify and would like to provide guidance on our support processes.

Priority technical support via "Contact Us" is available only for Dify Cloud Pro and Team subscribers.
If you are on a Pro or Team plan, please submit your request through Settings → Support → Contact Us in your dashboard.
When submitting the ticket, please do not remove the subscription verification details, as they are required for us to confirm your account status.

For Sandbox (Free Tier) users, we recommend consulting our comprehensive documentation at docs.dify.ai or submitting technical issues via GitHub at github.com/langgenius/dify/issues.

If you're interested in commercial collaboration or licensing, please email business@dify.ai with your company name, size, and specific use case. For verification purposes, kindly use your corporate email address when making business inquiries.

Please note that your use of Dify is permitted without additional commercial licensing when following our open source license terms and not creating products that directly compete with Dify's services. While not required, we appreciate "Powered by Dify" attribution in your implementations.

For efficient processing, we may be unable to respond to inquiries where the sender's identity cannot be verified. If you are a Dify partner, please contact us through your established partner channels.

Best regards,

The Dify Support Team
```

### 3. Self-hosted (non-Premium) handling
For `self_hosted` sub_type only:
- Do NOT route to ticket system
- Reply with X template as usual
- Add internal comment: "[AI] Self-hosted user - non-Premium, no ticket routing"

### 4. Close conversation
After sending the template reply:
- Call `front_close_conversation` to archive the conversation
- Do NOT create any drafts or additional replies

## Important Rules
- Always use `front_reply_with_template` for technical issues - do NOT use `front_create_draft`
- Only the X template should be used for all technical replies
- Archive the conversation after sending the template reply
- For self_hosted non-Premium users: no ticket routing needed, just reply and close