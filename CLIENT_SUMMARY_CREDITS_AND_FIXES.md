# Client Summary: Credit Usage & Issues Resolved

**Date:** February 2026  
**Purpose:** Explain Apollo credit usage and what was fixed in the Lead Automation system.

---

## 1. Why Are So Many Credits Being Used?

### What Uses Apollo Credits?

In our system, **credits are used mainly when we enrich contacts** (get their email addresses from Apollo). Here’s how it works:

| Action | Credits Used? |
|--------|----------------|
| **Searching for companies** (Level 1) | No – uses Google Places |
| **Searching for people at a company** (who works there) | **No** – Apollo search is free |
| **Getting contact emails** (enrichment) | **Yes – 1 credit per contact** |
| **Getting employee count** for a company | Yes – 1 credit per company (only when you filter by company size) |

So **the 1,664 credits you see** = roughly **1,664 contacts whose emails we fetched** in this billing period (Feb 7 – Mar 7, 2026).

### Why It Can Feel Like “Too Much”

- Before our fixes, we were sometimes enriching contacts that didn’t match your job titles, then filtering them out later. Those enriched contacts still used credits.
- We have now changed the flow so we **filter by your chosen job titles first**, then **only enrich the contacts that match**. That reduces wasted credits.

### What We Did to Reduce Credit Waste

1. **Filter before enrichment** – Only contacts matching your designations (e.g. CEO, HR, Director) are enriched.
2. **Check database first** – If we already have contacts for a company, we don’t call Apollo again for that company.
3. **Employee count only when needed** – We only fetch employee count when you use the “Employee Range” filter; otherwise we don’t use credits for that.
4. **No enrichment when there are 0 matches** – If no one matches your titles, we don’t enrich anyone (0 credits for that company).

---

## 2. Issues You Reported & What We Fixed

### Issue 1: “When I select 50 companies, I get 29 or 38”

**What was happening:**  
You selected 50 companies, but the system showed 29 or 38 contacts. This was due to a mix of:

- Some companies having **no contacts** in Apollo for the domain/name we use.
- Our **filters** (job title, etc.) removing people who didn’t match.
- Apollo sometimes returning **0 people** for a company domain, so we had nothing to show for that company.

**What we fixed:**

- We **relaxed Apollo-side filters** so Apollo returns more people per company; we then **filter strictly on our side** by your job titles. So you get more candidates that match.
- We added a **fallback search by company name** when search by website/domain returns 0 people. So more companies actually return contacts.
- We fixed a **bug** (missing `import`) that was causing the system to crash and show 0 contacts even when data existed.

**Result:** You should now see **more contacts per company** when they exist in Apollo, and fewer “0 contact” companies when we can find people by company name.

---

### Issue 2: “Level 3 numbers don’t match”

**What was happening:**  
Level 2 might show e.g. 40 contacts, but Level 3 showed a different number (e.g. more, or fewer). Reasons included:

- **All contacts** (including ones that didn’t match your job titles) were being saved and then shown in Level 3.
- The **contact count** was shown in the batch dropdown (e.g. “33 contacts”) and could be confusing or wrong in some cases.

**What we fixed:**

- **Level 2 now saves only contacts that match your chosen designations.** So what you see in Level 2 is what gets saved and then shown in Level 3.
- **Level 3 auto-loads the right batch** when you open “Send Campaign”, so you don’t have to manually pick from the dropdown to see your contacts.
- We **removed the contact count from the batch dropdown** (no more “33 contacts” in the label) to avoid mismatch confusion. The real count is shown in the Transfer Overview / contact list.

**Result:** Level 2 and Level 3 numbers should **match**: the same contacts you see in Level 2 are the ones available in Level 3 for the campaign.

---

### Issue 3: “Employee” or wrong titles showing in Level 3

**What was happening:**  
Level 3 sometimes showed “Employee” or other titles you didn’t search for.

**What we fixed:**  
We now **filter and save only contacts that match your job titles** (CEO, HR, Director, etc.) in Level 2. So Level 3 only shows those designations, not generic “Employee” contacts that didn’t match.

---

## 3. Quick Reference: What’s Better Now

| Before | After |
|--------|--------|
| Credits used even for contacts we later filtered out | We filter first; only matching contacts are enriched (fewer wasted credits) |
| Selecting 50 companies often gave 29 or 38 contacts | More contacts found per company (better search + company-name fallback) |
| Level 2 and Level 3 counts didn’t match | Level 2 and Level 3 show the same contacts and counts |
| Had to open dropdown in Level 3 to see contacts | Level 3 auto-loads the batch when you open Send Campaign |
| “33 contacts” and similar text in batch name caused confusion | Batch names no longer show contact count in the dropdown |
| 0 contacts even when companies had people | Bug fixed; fallback by company name when domain returns 0 |

---

## 4. Important Note: Payment Failure Banner

Your Apollo dashboard shows: **“Payment Failure. Please correct your billing information within 17 days to keep access to your account.”**

This is an **Apollo billing/account issue**, not something we can fix in the Lead Automation app. To avoid losing access and to keep credits working, please **update your billing details in Apollo** (Settings / Billing) before the deadline.

---

## 5. Summary for the Client (short version)

- **Credits:** The ~1,664 credits used = roughly 1,664 contact emails we fetched. We’ve reduced waste by filtering before enriching and by reusing data we already have.
- **50 companies → 29/38 contacts:** We improved how we search and added a fallback; you should get more contacts per company when Apollo has them.
- **Level 3 mismatch:** We now save and show only the contacts that match your job titles, and Level 3 auto-loads the batch and shows the same list as Level 2.
- **Payment failure:** Please update billing in Apollo before the deadline so the account and credits keep working.

If you want this in a shorter email or slide format, we can trim it down further.
