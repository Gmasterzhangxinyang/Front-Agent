# Support Inbox Historical Test Set - 50 Conversations

- Source inbox: Support (`inb_f9fvf`)
- Selection rule: latest 50 conversations returned by Front `/inboxes/inb_f9fvf/conversations?limit=50`
- Generated at: 2026-06-17 05:52:26 UTC
- Privacy: raw customer email addresses, domains, subjects, and message bodies are intentionally not stored in this repo file.
- Test execution should fetch full content from Front by `conversation_id` in a secure local run.

## Review Columns

- `selection_hint`: coarse hint derived from the Front subject only, used to keep the 50-case set diverse enough to review.
- `expected_route`: fill during manual review after reading the full conversation in Front.
- `actual_route`: record the new agent route during dry-run testing.
- `result`: pass/fail after review.

| # | conversation_id | created_at | status | selection_hint | expected_route | actual_route | result |
|---|---|---|---|---|---|---|---|
| 1 | `cnv_1ivl23bv` | 2026-06-17 04:43:03 UTC | archived | manual_review_unknown |  |  |  |
| 2 | `cnv_1ivku2u3` | 2026-06-17 03:37:42 UTC | archived | manual_review_unknown |  |  |  |
| 3 | `cnv_1ivffx7f` | 2026-06-16 19:19:27 UTC | archived | spam_ads_promotion |  |  |  |
| 4 | `cnv_1ivdxvvf` | 2026-06-16 17:42:47 UTC | unassigned | education |  |  |  |
| 5 | `cnv_1ivdhp5n` | 2026-06-16 17:13:54 UTC | archived | spam_ads_promotion |  |  |  |
| 6 | `cnv_1ivdejiz` | 2026-06-16 17:08:23 UTC | archived | spam_ads_promotion |  |  |  |
| 7 | `cnv_1ivddm8r` | 2026-06-16 17:06:52 UTC | archived | spam_ads_promotion |  |  |  |
| 8 | `cnv_1ivdd4nv` | 2026-06-16 17:06:09 UTC | archived | manual_review_unknown |  |  |  |
| 9 | `cnv_1ivcqgij` | 2026-06-16 16:29:39 UTC | archived | manual_review_unknown |  |  |  |
| 10 | `cnv_1ivblbbv` | 2026-06-16 15:27:32 UTC | archived | business_purchase |  |  |  |
| 11 | `cnv_1ivbk1gb` | 2026-06-16 15:25:42 UTC | archived | manual_review_unknown |  |  |  |
| 12 | `cnv_1ivbfuor` | 2026-06-16 15:19:14 UTC | archived | manual_review_unknown |  |  |  |
| 13 | `cnv_1iv7tdsr` | 2026-06-16 09:57:56 UTC | archived | manual_review_unknown |  |  |  |
| 14 | `cnv_1iutfgij` | 2026-06-15 06:43:33 UTC | archived | account |  |  |  |
| 15 | `cnv_1iv7pvff` | 2026-06-16 09:30:36 UTC | archived | manual_review_unknown |  |  |  |
| 16 | `cnv_1it70pi3` | 2026-06-09 12:14:11 UTC | archived | education |  |  |  |
| 17 | `cnv_1irixijf` | 2026-06-03 08:53:20 UTC | archived | education |  |  |  |
| 18 | `cnv_1iuwq6aj` | 2026-06-15 14:18:39 UTC | archived | education |  |  |  |
| 19 | `cnv_1iv785qz` | 2026-06-16 07:15:01 UTC | unassigned | spam_ads_promotion |  |  |  |
| 20 | `cnv_1iupslp7` | 2026-06-14 06:27:18 UTC | archived | spam_ads_promotion |  |  |  |
| 21 | `cnv_1iv668m3` | 2026-06-16 02:12:58 UTC | archived | manual_review_unknown |  |  |  |
| 22 | `cnv_1iv65fbv` | 2026-06-16 02:06:25 UTC | archived | manual_review_unknown |  |  |  |
| 23 | `cnv_1iv45x0b` | 2026-06-15 21:16:30 UTC | archived | education |  |  |  |
| 24 | `cnv_1iuzq9p7` | 2026-06-15 16:40:32 UTC | archived | spam_ads_promotion |  |  |  |
| 25 | `cnv_1iuzpxcr` | 2026-06-15 16:39:57 UTC | archived | spam_ads_promotion |  |  |  |
| 26 | `cnv_1iuz9mu3` | 2026-06-15 16:20:26 UTC | archived | spam_ads_promotion |  |  |  |
| 27 | `cnv_1iuul7a3` | 2026-06-15 11:43:15 UTC | archived | spam_ads_promotion |  |  |  |
| 28 | `cnv_1iuuhknv` | 2026-06-15 11:24:40 UTC | archived | partnership_marketing |  |  |  |
| 29 | `cnv_1iuu8cm3` | 2026-06-15 10:36:24 UTC | unassigned | technical |  |  |  |
| 30 | `cnv_1iuu215n` | 2026-06-15 09:52:40 UTC | archived | security |  |  |  |
| 31 | `cnv_1iutyj17` | 2026-06-15 09:23:03 UTC | archived | spam_ads_promotion |  |  |  |
| 32 | `cnv_1irvljdn` | 2026-06-04 03:27:04 UTC | archived | manual_review_unknown |  |  |  |
| 33 | `cnv_1iuttf2z` | 2026-06-15 08:45:29 UTC | archived | manual_review_unknown |  |  |  |
| 34 | `cnv_1iutquvv` | 2026-06-15 08:24:07 UTC | unassigned | business_purchase |  |  |  |
| 35 | `cnv_1itvvw0r` | 2026-06-11 06:01:14 UTC | archived | manual_review_unknown |  |  |  |
| 36 | `cnv_1iutew63` | 2026-06-15 06:36:43 UTC | archived | manual_review_unknown |  |  |  |
| 37 | `cnv_1iutab17` | 2026-06-15 05:54:27 UTC | archived | manual_review_unknown |  |  |  |
| 38 | `cnv_1iut5kyj` | 2026-06-15 05:03:00 UTC | archived | account |  |  |  |
| 39 | `cnv_1inpix7f` | 2026-05-20 09:17:47 UTC | archived | billing |  |  |  |
| 40 | `cnv_1iura0m3` | 2026-06-14 17:57:10 UTC | archived | technical |  |  |  |
| 41 | `cnv_1iuqa9qz` | 2026-06-14 11:59:44 UTC | archived | technical |  |  |  |
| 42 | `cnv_1irnz1y3` | 2026-06-03 16:17:48 UTC | archived | education |  |  |  |
| 43 | `cnv_1iumr2or` | 2026-06-13 07:02:07 UTC | archived | security |  |  |  |
| 44 | `cnv_1iul1q8r` | 2026-06-12 22:02:56 UTC | archived | account |  |  |  |
| 45 | `cnv_1iubworf` | 2026-06-12 09:46:42 UTC | archived | spam_ads_promotion |  |  |  |
| 46 | `cnv_1iubmom3` | 2026-06-12 08:43:20 UTC | archived | manual_review_unknown |  |  |  |
| 47 | `cnv_1iuahaaj` | 2026-06-12 05:23:04 UTC | archived | spam_ads_promotion |  |  |  |
| 48 | `cnv_1iuacvff` | 2026-06-12 05:03:07 UTC | archived | manual_review_unknown |  |  |  |
| 49 | `cnv_1iuac3h7` | 2026-06-12 05:00:32 UTC | archived | technical |  |  |  |
| 50 | `cnv_1iu9fl23` | 2026-06-12 02:49:21 UTC | archived | manual_review_unknown |  |  |  |
