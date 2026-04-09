---
name: post-linkedin
description: Draft and post business updates to LinkedIn with mandatory human approval before publishing.
tier: silver
triggers:
  - "post to linkedin"
  - "share on linkedin"
  - "publish linkedin update"
  - "create linkedin post"
  - "post on linkedin"
  - "linkedin post"
dependencies:
  - helpers/linkedin_poster.py
  - AI_Employee_Vault/Pending_Approval/
  - helpers/dashboard_updater.py
---

## Purpose

Draft a LinkedIn post on behalf of the user, route it through the Human-in-the-Loop
approval workflow, and publish it only after explicit human approval.

**NEVER auto-post to LinkedIn without approval. Every post MUST pass through
`Pending_Approval/` and be explicitly moved to `Approved/` by a human.**

---

## Triggers

This skill activates when the user says any of:

- "post to linkedin"
- "share on linkedin"
- "publish linkedin update"
- "create linkedin post"
- "post on linkedin"
- "linkedin post"

The text following the trigger phrase is treated as the post content or topic.

---

## Process

### Step 1 — Collect Post Content

Extract the post content from the user's message (everything after the trigger phrase).

If the user gave a topic rather than finished content (e.g., "share on LinkedIn about our Bronze tier completion"):
- Draft a professional post based on the topic
- Show the draft to the user and ask: "Here is the draft — reply with OK to submit for approval, or provide edits."
- Incorporate any edits before proceeding

If the user provided no content at all, ask:
> "What would you like to post to LinkedIn? Please provide the post content or topic."

### Step 2 — Validate Content

Before creating the approval file, check:

- Content is not empty
- Content is between 10 and 3000 characters (LinkedIn limit)
- Content does not contain: passwords, API keys, tokens, email addresses in raw form, or internal confidential data
- If any check fails, tell the user what needs fixing and stop

Flag for extra review (but do not block) if content contains:
- Financial figures or projections
- Client or partner names
- Pricing information
- Legal claims

### Step 3 — Create Approval File

Create a file at `AI_Employee_Vault/Pending_Approval/LINKEDIN_POST_<YYYYMMDD_HHMMSS>.md`
with this exact structure:

```
---
type: linkedin_post_approval
status: pending
created: <ISO timestamp>
expires: <ISO timestamp + 24 hours>
content_preview: <first 100 chars of post>
image_path: <path if provided, otherwise none>
---

# LinkedIn Post — Awaiting Approval

**Created:** <timestamp>
**Expires:** <timestamp + 24 hours>
**Status:** PENDING

---

## Post Content

<full post content here>

---

## Image

<image path, or "None">

---

## Approval Instructions

To **approve**: move this file to `Approved/`
To **reject**: move this file to `Rejected/` and add a reason below

### Rejection Reason (if rejecting)

_Add reason here before moving to Rejected/_

---

## Security Checks

- [ ] No credentials or tokens in content
- [ ] No confidential client data
- [ ] Tone is professional
- [ ] Content is accurate
```

Then tell the user:
> "Your LinkedIn post has been submitted for approval. Review it at:
> `Pending_Approval/LINKEDIN_POST_<timestamp>.md`
> Move the file to `Approved/` to publish, or to `Rejected/` to decline.
> This approval expires in 24 hours."

### Step 4 — Check for Approval

Poll the `Approved/` folder for the file. If running interactively, ask the user:
> "Have you approved the post? Say 'yes, approved' or 'rejected' to proceed."

When the user confirms approval (or the file appears in `Approved/`):

#### Step 4a — Publish the Post

Run the poster helper via the terminal:

    python helpers/linkedin_poster.py --content "<post content>" [--image "<image_path>"]

Or invoke `post_to_linkedin(content, image_path, vault_path)` from
`helpers/linkedin_poster.py`.

#### Step 4b — Handle the Result

**On success:**
- Log to `Vault/Logs/linkedin_posts.log`:
  `<timestamp> | SUCCESS | <content preview> | <post_url>`
- Update Dashboard: "LinkedIn post published — <content preview>"
- Move the approval file from `Approved/` to `Done/`
- Report to user:
  > "✅ Posted to LinkedIn successfully!
  > URL: <post_url>
  > Posted at: <timestamp>"

**On failure:**
- Log to `Vault/Logs/linkedin_posts.log`:
  `<timestamp> | FAILED | <content preview> | error: <error message>`
- Update Dashboard: "LinkedIn post FAILED — <error>"
- Leave approval file in `Approved/` for retry
- Report to user:
  > "❌ Post failed: <error message>
  > The approval file remains in `Approved/` — say 'retry linkedin post' to try again."

**On rate limit:**
- Report: "⏳ LinkedIn rate limit hit. Retry after <retry_after> seconds (<time>)."

### Step 5 — Handle Rejection

If the user says "rejected" or moves the file to `Rejected/`:
- Log to `Vault/Logs/linkedin_posts.log`:
  `<timestamp> | REJECTED | <content preview>`
- Update Dashboard: "LinkedIn post rejected — <content preview>"
- Move approval file to `Rejected/` (if not already moved)
- Report to user:
  > "Post rejected and archived in `Rejected/`. You can resubmit with modifications."

### Step 6 — Expiry

If the approval file has not been actioned within 24 hours, it is considered
auto-rejected. Note this in the Dashboard activity log and move it to `Rejected/`
with the reason "Approval timeout — 24 hours elapsed."

---

## Dashboard Updates

After every action, update `Dashboard.md`:

- Increment **Pending Approvals** counter when approval file is created
- Decrement **Pending Approvals** counter when approved or rejected
- Increment **Actions Approved** on publish success
- Increment **Actions Rejected** on rejection
- Add activity log entry with timestamp and outcome

---

## Security Rules

- **NEVER** call `linkedin_poster.py` without a file present in `Approved/`
- **NEVER** log the LinkedIn session cookies or any credentials
- **NEVER** post on behalf of the user without explicit approval
- **ALWAYS** validate content before creating the approval file
- Sensitive content flags (financials, client names, pricing) must be noted
  in the approval file so the human reviewer is aware

---

## Usage Examples

**Finished content:**
> "Post to LinkedIn: Excited to announce the completion of our AI Employee Bronze tier! 🎉"

**Topic-based (skill drafts first):**
> "Share on LinkedIn about our Bronze tier completion"

**With image:**
> "Post to LinkedIn: Check out our new dashboard — [image: screenshots/dashboard.png]"

---

## Error Reference

| Error | Meaning | Action |
|-------|---------|--------|
| No saved session | LinkedIn watcher not logged in | Run `linkedin_watcher.py` first |
| Session expired | Cookies stale | Re-run `linkedin_watcher.py` to log in |
| Rate limited | Too many requests | Wait `retry_after` seconds |
| Content too long | Over 3000 characters | Shorten the post |
| Post failed after 3 retries | Network/UI issue | Check internet and retry manually |
