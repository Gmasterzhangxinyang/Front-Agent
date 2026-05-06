# Skill: Email Classification

## Purpose
Classify an incoming support email into the correct category so the right handler can process it.

## Instructions
Read the full email content (including any attachments) and return a JSON classification result.

## Output Format (strict JSON)
```json
{
  "category": "<category>",
  "sub_type": "<sub_type or null>",
  "is_paid_user": <true/false>,
  "is_premium": <true/false>,
  "urgency": "<normal/high>",
  "sender_email": "<email address of sender>",
  "summary": "<one sentence summary of the user's issue>",
  "confidence": <0.0-1.0>,
  "flags": []
}
```

## Few-Shot Examples

### Example 1: Education Plan Rejection
**Email:** "Hi, I applied for the education plan but it was rejected. I'm a student at Stanford University, my school email is john@stanford.edu. Can you help me verify?"

**Classification:**
```json
{
  "category": "education",
  "sub_type": "rejected",
  "is_paid_user": false,
  "is_premium": false,
  "urgency": "normal",
  "sender_email": "john@stanford.edu",
  "summary": "Student from Stanford University requesting education plan verification after rejection",
  "confidence": 0.95,
  "flags": []
}
```

### Example 2: Technical Workflow Issue
**Email:** "My workflow keeps failing at the HTTP Request node. I'm getting a 500 error every time it tries to call the external API. I'm on the Pro plan."

**Classification:**
```json
{
  "category": "technical",
  "sub_type": "workflow_issue",
  "is_paid_user": true,
  "is_premium": false,
  "urgency": "normal",
  "sender_email": "user@company.com",
  "summary": "Pro user experiencing 500 error in workflow HTTP Request node",
  "confidence": 0.92,
  "flags": ["urgent_service_impact"]
}
```

### Example 3: Refund Request
**Email:** "I was charged twice for my Team plan subscription last month. Can I get a refund for the duplicate charge? My workspace ID is ws_abc123."

**Classification:**
```json
{
  "category": "billing",
  "sub_type": "duplicate_charge",
  "is_paid_user": true,
  "is_premium": false,
  "urgency": "normal",
  "sender_email": "user@company.com",
  "summary": "Team plan user requesting refund for duplicate charge",
  "confidence": 0.98,
  "flags": []
}
```

### Example 4: Account Login Issue
**Email:** "I can't log into my account. I'm not receiving the verification code email. I've checked my spam folder."

**Classification:**
```json
{
  "category": "account",
  "sub_type": "cant_login",
  "is_paid_user": false,
  "is_premium": false,
  "urgency": "high",
  "sender_email": "user@company.com",
  "summary": "User unable to log in, verification code email not received",
  "confidence": 0.96,
  "flags": ["urgent_service_impact"]
}
```

### Example 5: Spam/Promotional
**Email:** "Hi! We offer SEO services to boost your website ranking. Get 50% off this month! Reply to learn more."

**Classification:**
```json
{
  "category": "spam",
  "sub_type": null,
  "is_paid_user": false,
  "is_premium": false,
  "urgency": "normal",
  "sender_email": "marketing@seocompany.com",
  "summary": "Promotional email offering SEO services",
  "confidence": 0.99,
  "flags": []
}
```

## Categories and Sub-types

| category | sub_type | When to use |
|---|---|---|
| technical | workflow_issue | Workflow not working, step failing |
| technical | bug_report | Something broken, unexpected behavior |
| technical | how_to | How to do X, how to configure Y |
| technical | feasibility | Can Dify do X? Evaluating before purchase |
| technical | api_issue | API limits, API key, API usage |
| technical | outage | Service down, can't access Dify at all |
| technical | data_privacy | Questions about data storage, training, GDPR |
| technical | self_hosted | Self-hosted installation/config (non-Premium) |
| account | cant_login | Can't log in, not receiving verification code |
| account | delete_account | User wants to delete their account |
| account | transfer_account | User wants to transfer account to new email |
| account | change_email | Account works fine, wants to change email |
| account | account_anomaly | Quota wrong, plan changed unexpectedly |
| account | account_hacked | Account compromised, unauthorized access |
| account | merge_accounts | User wants to merge two accounts |
| purchase | enterprise | Asking about Enterprise plan |
| purchase | pro_team | Asking about Pro/Team/Premium pricing |
| purchase | promo_code | Asking for promo code, discount code, or holiday deals |
| purchase | reseller | Wants to become reseller or agent |
| education | rejected | Education plan application rejected |
| education | no_discount | Edu verified but discount not showing |
| billing | refund | Wants a refund |
| billing | duplicate_charge | Charged twice |
| billing | downgrade | Wants to downgrade or cancel subscription |
| billing | invoice | Invoice address or details |
| billing | other | Other billing questions |
| partnership | plugin | Plugin cooperation or bug |
| partnership | marketplace | Marketplace cooperation |
| partnership | plugin_takedown | Wants to take down their own plugin |
| security | general | Security concern |
| security | urgent | Active breach, data leak, critical vulnerability |
| spam | null | Promotional, advertising, unsolicited sales |
| legal | null | Lawyer letter, legal threat, lawsuit |
| roadmap | null | Asking about roadmap or feature release dates |
| data_export | null | Requesting export of their personal data |
| unclear | null | Cannot determine category with confidence |

## Paid User Detection
- Check email body/footer for: `Current Plan: professional` or `Current Plan: team`
- If found → `is_paid_user: true`
- If footer says `Current Plan: premium` → `is_premium: true` (self-hosted licensed user)
- If no footer → `is_paid_user: false`, `is_premium: false`

## Flags (add to flags array when applicable)
- `legal_threat` — email contains legal threats or mentions lawyers
- `vip_company` — sender appears to be from a very large/well-known company
- `emotional` — user is angry, upset, or threatening to post publicly
- `repeated_email` — user mentions they've emailed before without response
- `has_refund_request` — email mentions refund even if primary category is different
- `urgent_service_impact` — issue is actively blocking user's work

## Important Rules
- Only classify as `is_paid_user: true` if there is clear evidence in the footer
- For `feasibility` sub_type: user is evaluating Dify before purchasing
- `self_hosted` non-Premium users should NOT be routed to ticket system
- When in doubt, use `unclear`
