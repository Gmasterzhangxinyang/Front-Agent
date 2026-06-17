# Skill Test Cases

Purpose: manual end-to-end testing from the Support inbox. Send each email as a new conversation unless the case says "follow-up reply".

Check three things for every case:

1. Classification category/sub_type is correct.
2. Tool action is correct: draft, Front forward, inbox move, Linear ticket, or spam close.
3. Conversation stays open unless the expected result says spam close.

Do not use real customer data in these tests.

## Technical

### TECH-01 workflow_issue

Expected: `technical/workflow_issue`, create Front draft; paid users go to ticket path, non-paid users go to community/GitHub, keep open.

```text
Subject: HTTP Request node keeps failing
From: test-tech-workflow@example.com

Hi Dify team,

My workflow fails at the HTTP Request node every time it calls our internal API.
The node returns 500, but the same request works in Postman.
Workspace ID: ws_test_tech_001
Current Plan: professional

Can you help me troubleshoot this?
```

### TECH-02 api_issue

Expected: `technical/api_issue`, create Front draft guiding paid user to Settings -> Support -> Contact Us ticket path, keep open.

```text
Subject: API key returns unauthorized
From: test-tech-api@example.com

Hello,

My Dify API key suddenly returns 401 unauthorized when I call the chat-messages endpoint.
I regenerated the key but it still fails.
Current Plan: team

Please advise.
```

### TECH-03 self_hosted

Expected: `technical/self_hosted`, create guidance draft pointing non-paid/Community users to docs, community, and GitHub issue; no Linear ticket, keep open.

```text
Subject: Self-hosted docker compose cannot start
From: test-selfhosted@example.com

Hi,

I installed the open-source self-hosted Dify with docker compose.
The api container keeps restarting after I changed the .env file.
Current Plan: sandbox

What should I check?
```

### TECH-04 outage

Expected: `technical/outage`, create Front draft, keep open.

```text
Subject: Cannot access Dify cloud
From: test-outage@example.com

Hi support,

I cannot access cloud.dify.ai from our office network and my team cannot open the console either.
This is blocking our production workflow.
Current Plan: team
```

## Account

### ACC-01 cant_login paid user

Expected: `account/cant_login`, create Linear ticket, Front forward to Bobby with Linear link, create "processing" draft, keep open.

```text
Subject: Cannot log in to my Pro account
From: test-account-paid@example.com

Hi,

I cannot log in to my Dify account. I do not receive the verification code email.
I checked spam and tried again several times.
Current Plan: professional
```

### ACC-02 cant_login unclear paid status

Expected: `account/cant_login`, draft asking whether they use Dify Cloud/SaaS or self-hosted and asking current plan, state `awaiting_deployment_and_plan_confirmation`, keep open.

```text
Subject: Login verification code not received
From: test-account-free@example.com

Hello,

I cannot log in because the verification code never arrives.
I checked spam and the email address is correct.
Can you fix it?
```

### ACC-03 cant_login education email expired

Expected: `account/cant_login`, draft asking whether school email expired, state waiting for email-expired confirmation, keep open.

```text
Subject: Cannot receive login code on university email
From: test-student@stanford.edu

Hi,

I cannot receive the Dify login verification code on my school email.
I graduated recently and I am not sure whether my university mailbox still works.
Can you help me get back into my account?
```

### ACC-04 delete_account can log in

Expected: `account/delete_account`, create self-service deletion draft, keep open.

```text
Subject: Delete my Dify account
From: test-delete-login@example.com

Hi,

I can still log in to my Dify account, but I want to delete the account permanently.
Please tell me how to do it.
```

### ACC-05 delete_account cannot log in

Expected: `account/delete_account`, create identity verification draft, state awaiting identity verification, keep open.

```text
Subject: Delete account but I cannot log in
From: test-delete-nologin@example.com

Hello,

I want to delete my Dify account but I cannot log in anymore.
The account email is old-account@example.com.
Please delete it for me.
```

### ACC-06 change_email cannot log in

Expected: `account/change_email` or `account/transfer_account`, identity verification draft, keep open.

```text
Subject: Change account email
From: test-change-email@example.com

Hi,

I cannot access my old email old-email@example.com anymore.
Please move my Dify account to new-email@example.com.
I cannot log in to change it myself.
```

### ACC-07 account_anomaly

Expected: `account/account_anomaly`, create Linear ticket and Front draft, keep open.

```text
Subject: My paid quota disappeared
From: test-account-anomaly@example.com

Hi,

My workspace was on the Team plan but today the quota looks like a free account.
The billing page still shows an active subscription.
Current Plan: team
```

### ACC-08 account_hacked

Expected: `account/account_hacked` unless active breach is security; create urgent draft and likely Linear ticket, keep open.

```text
Subject: Someone accessed my account
From: test-account-hacked@example.com

Hi,

I saw unknown workflows created in my Dify workspace and my API key was changed.
I still control this email address, but I think my account was compromised.
Current Plan: professional
```

### ACC-09 merge_accounts

Expected: `account/merge_accounts`, create draft saying merge is not currently available, keep open.

```text
Subject: Merge two Dify accounts
From: test-merge@example.com

Hello,

I have two Dify accounts under personal@example.com and work@example.com.
Can you merge them into one account and keep all workspaces?
```

## Education

### EDU-01 rejected with university info

Expected: `education/rejected`, Linear ticket, Front forward to `sybil@dify.ai` with Linear link, create customer draft, keep open.

```text
Subject: Education plan rejected
From: test-edu-university@mit.edu

Hi,

My education plan application was rejected.
I am a student at Massachusetts Institute of Technology.
My school email domain is mit.edu.
Can you review it again?
```

### EDU-02 rejected with personal email

Expected: `education/rejected`, draft asking for school domain, state awaiting school info, keep open.

```text
Subject: Education discount rejected
From: test-edu-gmail@gmail.com

Hi,

I applied for the education plan but it was rejected.
I study at Stanford University, but I used this Gmail address.
Can you approve the education discount?
```

### EDU-03 rejected K-12

Expected: `education/rejected`, not-eligible draft, keep open.

```text
Subject: Education plan for high school
From: test-k12@example.edu

Hello,

I am a teacher at Lincoln High School.
Our email domain is lincolnhigh.edu.
Can our school get the Dify education plan?
```

### EDU-04 missing school info

Expected: `education/rejected`, draft asking for school full name and official email domain, state awaiting_school_info, keep open.

```text
Subject: Help with education plan
From: test-edu-missing@example.com

Hi,

My education application did not pass.
Can you help me check why?
```

### EDU-05 no_discount with edu badge

Expected: `education/no_discount`, create billing guidance draft, keep open.

```text
Subject: Edu verified but discount not applied
From: test-edu-discount@berkeley.edu

Hi,

My account shows the edu badge, but the checkout page still asks me to pay for Pro.
Why is the 100% education discount not applied?
```

### EDU-06 graduated email expired

Expected: `education/email_expired_graduated`, identity verification draft, state awaiting_identity_verification, keep open.

```text
Subject: Graduated and lost school email
From: test-edu-graduated@gmail.com

Hello,

I had an education account with old-student@university.edu, but I graduated and the school email no longer works.
Please move my education account to this new email address.
```

### EDU-07 cancel education subscription

Expected: `education/cancel_subscription`, create no-auto-renew explanation draft, keep open.

```text
Subject: Cancel education subscription
From: test-edu-cancel@ucla.edu

Hi,

I am using the Dify education plan and want to cancel it so I will not be charged later.
How do I cancel the subscription?
```

## Billing

### BILL-01 refund

Expected: `billing/refund`, create refund guidance draft, keep open.

```text
Subject: Refund request
From: test-refund@example.com

Hi,

I bought the Pro plan by mistake and would like a refund.
The charge was made yesterday with the card ending in 4242.
Current Plan: professional
```

### BILL-02 duplicate_charge

Expected: `billing/duplicate_charge`, create billing guidance draft, keep open.

```text
Subject: Charged twice for Team plan
From: test-duplicate-charge@example.com

Hello,

I was charged twice for the same Team plan subscription this month.
Workspace ID: ws_billing_test_002
Current Plan: team
```

### BILL-03 downgrade

Expected: `billing/downgrade`, create self-service downgrade draft, keep open.

```text
Subject: Downgrade my subscription
From: test-downgrade@example.com

Hi,

Please help me downgrade my Team plan to the free Sandbox plan before the next billing cycle.
Current Plan: team
```

### BILL-04 invoice

Expected: `billing/invoice`, create invoice self-service draft, keep open.

```text
Subject: Need invoice with company details
From: test-invoice@example.com

Hello,

I need an invoice for our Dify subscription with our company name and tax ID.
Where can I update the invoice details?
Current Plan: professional
```

## Purchase

### PUR-01 enterprise

Expected: `purchase/enterprise` or `business/enterprise_inquiry` depending classifier; no customer send. If purchase, create enterprise inquiry draft. If business, route to Business flow.

```text
Subject: Enterprise plan pricing and SLA
From: test-enterprise@example.com

Hi,

We are evaluating Dify Enterprise for a 500-person company.
We need SSO, SLA, dedicated support, and commercial redistribution rights.
Can we schedule a sales call and get a quote?
```

### PUR-02 pro_team

Expected: `purchase/pro_team`, create pricing guidance draft, keep open.

```text
Subject: Difference between Pro and Team plan
From: test-pro-team@example.com

Hello,

What is the difference between Pro and Team?
We are a small team of 6 people and want to know which plan to buy.
```

### PUR-03 promo_code

Expected: `purchase/promo_code`, create no-promo-code draft, keep open.

```text
Subject: Do you have a promo code?
From: test-promo@example.com

Hi,

Do you have any discount code or Black Friday coupon for the Pro plan?
```

### PUR-04 reseller

Expected: `purchase/reseller` or `partnership/partnership`; should forward original thread to `marketing@dify.ai`, keep open. A draft may be created only if purchase skill handles it.

```text
Subject: Become a Dify reseller
From: test-reseller@example.com

Hello,

Our company wants to become a Dify reseller in Southeast Asia.
Please share your reseller program and partnership process.
```

## Partnership / Marketplace / Community

### PART-01 marketplace plugin listing

Expected: `partnership/marketplace` or `partnership/plugin`, Front forward to `marketing@dify.ai` with original thread and summary, no customer draft, keep open.

```text
Subject: Publish our plugin on Dify Marketplace
From: test-marketplace-plugin@example.com

Hi Dify team,

We built a connector plugin and want to list it on the Dify Marketplace.
Please let us know the submission and review process.
```

### PART-02 plugin takedown

Expected: `partnership/plugin_takedown`, Front forward to `marketing@dify.ai`, no customer draft, keep open.

```text
Subject: Remove my plugin from Marketplace
From: test-plugin-takedown@example.com

Hello,

I am the maintainer of the Example Connector plugin.
Please remove it from the Dify Marketplace because we are discontinuing support.
```

### PART-03 community cooperation

Expected: `partnership/community`, Front forward to `marketing@dify.ai`, no customer draft, keep open.

```text
Subject: Community event cooperation
From: test-community@example.com

Hi,

We run an AI developer community and want to host a Dify workshop with your team.
Who should we coordinate with?
```

## Marketing

### MKT-01 campaign collaboration

Expected: `marketing/collaboration` or spam if unsolicited ad-like; preferred route for real collaboration is forward/move to Marketing, no customer draft, keep open.

```text
Subject: Joint campaign collaboration proposal
From: test-marketing-collab@example.com

Hi Dify marketing team,

We are organizing an AI builder campaign and would like Dify to join as a partner.
This is not a paid ad package; we want to discuss a joint campaign for developers.
```

### MKT-02 event sponsorship request

Expected: If it is asking Dify to buy sponsorship, likely `spam`; if genuine known partner event, `marketing/event`. Check that unsolicited ads close as spam.

```text
Subject: Sponsorship package for AI Summit
From: test-event-sponsor@example.com

Hello,

We are selling sponsorship packages for AI Summit 2026.
Gold sponsorship is $20,000 and includes booth, logo placement, and email promotion.
Reply today to reserve your slot.
```

## Security

### SEC-01 vulnerability report

Expected: `security/general` or `security/urgent`, move to Front inbox `Security`, no customer draft, keep open.

```text
Subject: Responsible disclosure: possible token exposure
From: test-security@example.com

Hi security team,

I found a possible vulnerability where API tokens may be exposed in workflow execution logs.
I can share reproduction steps privately.
Please route this to your security team.
```

### SEC-02 active data leak

Expected: `security/urgent`, move to Front inbox `Security`, no customer draft, keep open.

```text
Subject: Urgent: possible data leak in workspace
From: test-security-urgent@example.com

Hello,

We believe another user may be able to see data from our workspace.
This may be an active data leak and needs immediate security review.
Current Plan: team
```

## Legal

### LEGAL-01 lawyer letter

Expected: `legal/null` or legal_threat flag, Front forward to `geyan@dify.ai` with original thread and summary, no customer draft, keep open.

```text
Subject: Formal legal notice
From: test-legal@example.com

To Dify,

Our lawyer has advised us to send this formal notice regarding unauthorized use of our trademark.
If this is not resolved within 7 days, we will proceed with legal action.
Please have your legal representative contact us.
```

### LEGAL-02 legal threat mixed with refund

Expected: legal route wins because of legal_threat flag; forward to `geyan@dify.ai`, no refund draft, keep open.

```text
Subject: Refund or I will contact my lawyer
From: test-legal-refund@example.com

Hi,

I want a refund for my subscription. If you do not refund me this week,
I will ask my lawyer to file a claim against Dify.
Current Plan: professional
```

## Spam

### SPAM-01 SEO sales

Expected: `spam/null`, auto close/archive, no draft, no forward.

```text
Subject: Boost your SEO ranking
From: test-spam-seo@example.com

Hi,

We can get Dify 10,000 backlinks and first-page Google ranking in 30 days.
Special 50% discount this week only.
Reply now to buy our SEO package.
```

### SPAM-02 paid guest post

Expected: `spam/null`, auto close/archive, no draft, no forward.

```text
Subject: Paid guest post opportunity
From: test-spam-guestpost@example.com

Hello,

I want to publish a paid guest post on your website with do-follow links.
Please send your price list for sponsored content.
```

## Roadmap

### ROAD-01 feature timeline

Expected: `roadmap/null`, create roadmap guidance draft, keep open.

```text
Subject: When will multi-tenancy be available?
From: test-roadmap@example.com

Hi,

Do you have a roadmap or release date for multi-tenancy in the self-hosted version?
We are waiting for this feature before adopting Dify.
```

## Investment

### INV-01 investor inquiry

Expected: `investment/fundraising`, Front forward to Claudia, also notify Bobby via Front forward, no customer draft, keep open.

```text
Subject: Investment discussion with Dify
From: test-investor@example.com

Hi,

I am a partner at Example Ventures.
We would like to discuss Dify's fundraising plans and potential investment opportunities.
Please connect us with the person handling investor relations.
```

## Business

### BUS-01 procurement / vendor registration

Expected: `business/enterprise_inquiry`, route to Business flow, no customer draft, keep open.

```text
Subject: Vendor registration for enterprise purchase
From: test-procurement@example.com

Hello,

We are preparing to purchase Dify for our enterprise team.
Please complete our vendor registration form and provide your security questionnaire, DPA, and quote.
```

## Data Export

### DATA-01 personal data export

Expected: `data_export/null`, create data export guidance draft, keep open.

```text
Subject: Export all my personal data
From: test-data-export@example.com

Hi,

I would like to export all personal data associated with my Dify account,
including profile information, workspace metadata, and usage records.
Please tell me how to get a copy.
```

## Unclear

### UNCLEAR-01 not enough information

Expected: `unclear/null`, Front forward to `bobby@dify.ai` for manual review, no customer draft, keep open.

```text
Subject: Need help
From: test-unclear@example.com

Hi,

It does not work. Please fix it.
```

## Multi-turn Follow-up Tests

Use these only after creating the matching initial conversation above.

### FOLLOW-01 account SaaS plan confirmation

Start with `ACC-02`, then reply in the same thread:

Expected: detect previous state `awaiting_deployment_and_plan_confirmation`; create Linear ticket, forward to Bobby with Linear link, create processing draft, keep open.

```text
Yes, I am using Dify Cloud/SaaS on the Pro plan. The login code still does not arrive.
Current Plan: professional
```

### FOLLOW-02 education missing school info

Start with `EDU-04`, then reply in the same thread:

Expected: detect previous state `awaiting_school_info`; create Linear ticket, forward to Sybil with Linear link, create customer draft, keep open.

```text
My school is University of Washington.
The official email domain is washington.edu.
```

### FOLLOW-03 delete account identity verification

Start with `ACC-05`, then reply in the same thread:

Expected: detect previous state `awaiting_identity_verification`; if accepted, create Linear ticket and customer draft, keep open.

```text
I am replying from the original account email and confirm I want to delete the account permanently.
Account email: test-delete-nologin@example.com
```

### FOLLOW-04 education personal email still wrong

Start with `EDU-02`, then reply in the same thread:

Expected: keep `awaiting_school_info`; draft again asking for official school email domain, keep open.

```text
I only have my Gmail address. Please approve my education plan with test-edu-gmail@gmail.com.
```

## Expected Tool Summary

| Area | Expected tool/action |
|---|---|
| Technical | `front_create_draft`, `state_set`, keep open |
| Account | `front_create_draft`; paid/login legacy handoff goes to Bobby; some verified actions create Linear |
| Education eligible review | `linear_create_ticket` then `front_forward_to_sybil` then draft, keep open |
| Education ineligible/missing info | `front_create_draft`, keep open |
| Billing | `front_create_draft`, keep open |
| Purchase | mostly `front_create_draft`; reseller may forward to `marketing@dify.ai` |
| Partnership/Marketplace/Community | `front_forward_to_community` or `front_forward_to_partnerships` to `marketing@dify.ai`, keep open |
| Marketing | `front_forward_to_marketing` or deterministic marketing forward, keep open |
| Security | `front_forward_to_security`, target inbox `Security`, keep open |
| Legal | `front_forward_to_legal` to `geyan@dify.ai`, keep open |
| Spam | deterministic `front_close_conversation`, only case that closes |
| Roadmap | `front_create_draft`, keep open |
| Investment | `front_forward_to_investment`; Bobby may also receive internal forward; keep open |
| Business | business handoff flow, no customer draft |
| Data export | `front_create_draft`, keep open |
| Unclear | `front_forward_to_bobby`, no customer draft, keep open |
