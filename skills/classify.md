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
  "flags": [],
  "secondary_intents": [],
  "evidence": ["<short phrases from the email that support the classification>"]
}
```

Return only the JSON object. Do not wrap it in Markdown and do not add explanation text.

## Few-Shot Examples

Every example below includes all required fields. Follow this shape exactly. Use JSON `null`, not the string `"null"`.

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
  "flags": [],
  "secondary_intents": [],
  "evidence": ["education plan was rejected", "student at Stanford University", "john@stanford.edu"]
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
  "urgency": "high",
  "sender_email": "user@company.com",
  "summary": "Pro user experiencing repeated 500 errors in a workflow HTTP Request node",
  "confidence": 0.92,
  "flags": ["urgent_service_impact"],
  "secondary_intents": [],
  "evidence": ["workflow keeps failing", "HTTP Request node", "Pro plan"]
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
  "summary": "Team plan user requesting refund for a duplicate charge",
  "confidence": 0.98,
  "flags": ["has_refund_request"],
  "secondary_intents": [],
  "evidence": ["charged twice", "Team plan", "workspace ID is ws_abc123"]
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
  "summary": "User cannot log in because verification code email is not received",
  "confidence": 0.96,
  "flags": ["urgent_service_impact"],
  "secondary_intents": [],
  "evidence": ["can't log into my account", "not receiving the verification code", "checked my spam folder"]
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
  "flags": [],
  "secondary_intents": [],
  "evidence": ["offer SEO services", "boost your website ranking", "Get 50% off"]
}
```

### Bobby-Confirmed Example
**Email summary:** User requesting refund (message in Chinese: 需要退款)

**Classification:**
```json
{
  "category": "billing",
  "sub_type": "refund",
  "is_paid_user": false,
  "is_premium": false,
  "urgency": "normal",
  "sender_email": "",
  "summary": "User is requesting a refund",
  "confidence": 1.0,
  "flags": ["has_refund_request"],
  "secondary_intents": [],
  "evidence": ["需要退款"]
}
```

## Routing-Oriented Classification Rules

- Pick the category that determines the immediate operational route.
- If the email has mixed intents, set the primary `category` to the highest-risk or most actionable intent and put the rest in `secondary_intents`.
- If the sender is offering ads, SEO, backlinks, guest posts, generic promotion packages, lead generation, or other unsolicited vendor services, classify as `spam` even if the text mentions marketing or partnership.
- Classify YouTube/video/podcast/newsletter/content creator or media channel collaboration pitches as `marketing` with sub_type `collaboration`, unless the email is clearly an unrelated mass ad service pitch. These should be moved to the Marketing inbox, not auto-closed as spam.
- Classify Marketplace/plugin/template ecosystem cooperation as `partnership`; that route is forwarded to `marketing@dify.ai` by the system.
- Classify security reports, vulnerabilities, abuse reports, data leaks, hacked accounts with active compromise, or responsible disclosure as `security` unless the primary issue is ordinary account login help.
- Use `unclear` when the email lacks enough evidence to choose a route. Do not force a category.
- `evidence` must contain short non-sensitive phrases that justify the route.
- `confidence` is for review and evaluation only; do not use a numeric threshold to choose the route.

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
| education | cancel_subscription | Education plan user wants to cancel/not renew |
| billing | refund | Wants a refund |
| billing | duplicate_charge | Charged twice |
| billing | downgrade | Wants to downgrade or cancel subscription |
| billing | invoice | Invoice address or details |
| billing | other | Other billing questions |
| partnership | plugin | Plugin cooperation or bug |
| partnership | marketplace | Marketplace cooperation |
| partnership | plugin_takedown | Wants to take down their own plugin |
| marketing | campaign | Marketing campaigns, promotional events |
| marketing | collaboration | Marketing collaboration inquiries |
| marketing | event | Marketing events or sponsorship |
| security | general | Security concern |
| security | urgent | Active breach, data leak, critical vulnerability |
| spam | null | Promotional, advertising, unsolicited sales |
| legal | null | Lawyer letter, legal threat, lawsuit |
| roadmap | null | Asking about roadmap or feature release dates |
| investment | fundraising | Investment inquiries, funding, VC, investor relations |
| business | enterprise_inquiry | Enterprise plan, sales, business development, demo requests |
| data_export | null | Requesting export of their personal data |
| unclear | null | Cannot determine category with confidence |

## Paid User Detection
- Check email body/footer for: `Current Plan: professional` or `Current Plan: team`
- If found → `is_paid_user: true`
- If footer says `Current Plan: premium` → `is_premium: true` (self-hosted licensed user)
- If no footer → `is_paid_user: false`, `is_premium: false`

## Additional Output Fields

- `secondary_intents`: array of other possible categories present in the email; keep empty if there is only one intent.
- `evidence`: 1-3 short phrases from the email that support the classification. Do not include full private messages.

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
