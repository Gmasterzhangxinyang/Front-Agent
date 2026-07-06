# Skill: Recruiting / Careers

## Purpose
Handle candidate job applications, internship requests, resume submissions, portfolio introductions, and questions about open roles.

## Draft Quality Bar
- Write concise, professional English unless the user wrote primarily in another language.
- Answer only what the email supports. Do not invent hiring status, role availability, recruiter names, interview timelines, or feedback.
- If required facts are missing, ask for the minimum specific information needed instead of guessing.
- Do not mention internal tools, Linear, Sybil, Bobby, action logs, routing, or internal handoffs in customer-facing drafts.
- Do not promise that an application will be reviewed, shortlisted, forwarded, or receive a response.
- End with a clear next step.

## Steps by Sub-type

### job_application / internship / careers_question / general
1. Call `front_create_draft` with a polite careers-channel reply.
2. Call `state_set` with step="draft_created", waiting=false.
3. Keep the conversation open for Bobby to review the draft.

## Reply Template

```
Dear [Candidate Name / there],

Thank you for your interest in Dify and for sharing your background with us.

For career opportunities, please check the open roles listed on Dify's official careers page and apply through the role that best matches your experience. Applications sent through the careers channel are the best way for the hiring team to review your profile.

If there is no suitable opening at the moment, please keep an eye on future updates. We are not able to guarantee individual review or follow-up for applications sent to the support inbox.

Best regards,
Dify Support Team
```

## Important Rules
- Use this skill for candidates applying to Dify, students asking for internships, or people sending resumes/portfolios.
- Do not create Linear tickets.
- Do not forward to Bobby by default. Create a draft for review.
- If the sender is a recruiter, staffing agency, outsourcing provider, or vendor selling hiring services, this is unsolicited vendor outreach and should be classified as `spam`, not `recruiting`.
