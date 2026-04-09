---
name: post-linkedin
description: "Draft and post business updates to LinkedIn with mandatory human approval before publishing."
tier: silver
triggers:
  - "post to linkedin"
  - "share on linkedin"
  - "publish linkedin update"
  - "create linkedin post"
  - "linkedin post about"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  session_dir: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/.credentials/linkedin_session"
  log_file: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/logs/linkedin_posts.log"
  approval_expiry_hours: 24
  max_content_length: 3000
---

# Skill: post-linkedin

This skill accepts a LinkedIn post from the user, creates a human-approval file
in `Pending_Approval/`, and only publishes to LinkedIn after a human explicitly
moves that file to `Approved/`. It calls `helpers/linkedin_poster.py` for the
actual browser automation. Auto-posting is strictly forbidden.

---

## Purpose

- Provide a safe, auditable path for publishing to LinkedIn — no accidental posts
- Enforce Human-in-the-Loop (HITL) review for every piece of outbound content
- Support optional image attachments for richer posts
- Log every outcome (success, failure, rejection) to `logs/linkedin_posts.log`
- Keep the Dashboard accurate with pending/approved/rejected counters

---

## Process

### Step 1 — Collect post content

Extract everything after the trigger phrase as the post content.

If the user gave a topic rather than finished text (e.g. "share on LinkedIn about our hackathon"):
- Draft a professional post based on the topic
- Show the draft and ask: "Here is the draft — reply OK to submit for approval, or provide edits."
- Incorporate edits before continuing

If no content was given at all, ask:
> "What would you like to post to LinkedIn? Provide the post text or a topic to draft from."

If the user's message includes an image reference (e.g. "with the screenshot at screenshots/dashboard.png"), capture the image path.

### Step 2 — Validate content

Check all of the following before creating any file:

- Content is not empty
- Content is 10–3000 characters (LinkedIn hard limit)
- Content does not contain raw credentials, API keys, or tokens
- Content does not contain confidential internal data

If any check fails, tell the user exactly what needs fixing and stop.

Flag for extra human review (note in approval file, do not block) if content contains:
- Financial figures or projections
- Client or partner names
- Pricing information
- Legal claims

### Step 3 — Create approval file

Create `AI_Employee_Vault/Pending_Approval/LINKEDIN_POST_<YYYYMMDD_HHMMSS>.md`
with this exact structure:

```
---
action_type: linkedin_post
created: <ISO timestamp, e.g. 2026-04-09T15:45:00>
expires: <ISO timestamp + 24 hours>
status: pending
priority: normal
---

# APPROVAL REQUIRED: LinkedIn Post

## Post Content
<full post text>

## Image
<absolute image path, or "None">

## To Approve
Move this file to: Approved/

## To Reject
Move this file to: Rejected/ (and add rejection reason below)

## Rejection Reason (if rejected)
[Human adds reason here]

## Auto-Reject
This approval expires in 24 hours and will auto-reject if not decided.
```

If the content was flagged in Step 2, append a `## Review Flags` section listing the concerns so the human reviewer sees them.

After writing the file, tell the user:
> "Your LinkedIn post has been submitted for approval.
> File: `Pending_Approval/LINKEDIN_POST_<timestamp>.md`
> Move it to `Approved/` to publish, or to `Rejected/` to cancel.
> This approval expires in 24 hours."

Update the Dashboard: increment **Pending Approvals** counter and add an activity entry.

### Step 4 — Wait for human decision

Ask the user:
> "Have you reviewed and approved the post? Reply 'approved' to publish or 'rejected' to cancel."

Do not call the poster helper until the user confirms. This is the HITL gate.

#### Step 4a — On approval

Read the post content and image path from the approval file in `Approved/`.

Call `helpers/linkedin_poster.py` with those values (see How to Run).

**On success:**
- Log to `logs/linkedin_posts.log`:
  `[<timestamp>] [SUCCESS] <first 50 chars of content>… | URL: <post_url>`
- Update Dashboard: decrement Pending Approvals, increment Actions Approved, add activity entry
- Move the file from `Approved/` to `Done/`
- Report to the user:
  > "Posted to LinkedIn successfully!
  > URL: <post_url>
  > Posted at: <timestamp>"

**On failure:**
- Log to `logs/linkedin_posts.log`:
  `[<timestamp>] [FAILED] <first 50 chars>… | URL: —`
- Update Dashboard: note failure in activity log
- Leave the file in `Approved/` so the user can retry
- Report to the user:
  > "Post failed: <error message>
  > The approval file remains in Approved/ — say 'retry linkedin post' to try again."

**On rate limit:**
- Report: "LinkedIn rate limit detected. Retry after <retry_after> seconds."

#### Step 4b — On rejection

- Move the approval file to `Rejected/`
- Log to `logs/linkedin_posts.log`:
  `[<timestamp>] [REJECTED] <first 50 chars>… | URL: —`
- Update Dashboard: decrement Pending Approvals, increment Actions Rejected
- Report to the user:
  > "Post rejected and archived in Rejected/. Resubmit with modifications anytime."

### Step 5 — Handle expiry

If 24 hours pass with no decision, auto-reject the file:
- Move it from `Pending_Approval/` to `Rejected/` with reason "Approval timeout — 24 hours elapsed"
- Log the rejection
- Update Dashboard

---

## How to Run

The skill calls `helpers/linkedin_poster.py` after human approval is confirmed.
Do not run this file before approval is given.

```
Module:   helpers.linkedin_poster
Function: post_to_linkedin(content, image_path, vault_path, session_dir)

Arguments:
  content      — full post text read from the approved file
  image_path   — image path from the approved file, or None
  vault_path   — from config.vault_path
  session_dir  — from config.session_dir

Returns dict:
  success    (bool)
  post_url   (str | None)
  post_id    (str | None)
  timestamp  (str, ISO UTC)
  error      (str | None)
```

Session file required: `.credentials/linkedin_session/context.json`
This is created by running `watchers/linkedin_watcher.py` for the first time.

Error conditions from the helper:
- `"LinkedIn session not found. Run watcher first."` → session file absent
- `"LinkedIn session expired. Please re-login."` → session stale, re-run watcher
- `"Rate limited by LinkedIn. Try again later."` → back off and retry later
- Any other error string → post failed, user should retry

---

## Output — Vault Card Format

Approval file written to `Pending_Approval/`:

```yaml
---
action_type: linkedin_post
created: 2026-04-09T15:45:00
expires: 2026-04-10T15:45:00
status: pending
priority: normal
---
```

No separate vault card is created for the post result — the approval file itself
(moved to `Done/` or `Rejected/`) serves as the permanent record.

### Priority rules

All LinkedIn post approvals use `priority: normal` by default.
Set `priority: high` if the content was flagged during Step 2 validation
(financial figures, client names, legal claims).

---

## Expected Output

**When a post is submitted for approval:**

```
LinkedIn post submitted for approval.
File: Pending_Approval/LINKEDIN_POST_20260409_154500.md
Move to Approved/ to publish or Rejected/ to cancel.
Expires: 2026-04-10T15:45:00 (24 hours)
```

**When the post publishes successfully:**

```
Posted to LinkedIn successfully!
URL: https://www.linkedin.com/feed/update/urn:li:activity:1234567890
Posted at: 2026-04-09T15:47:32
Approval file moved to Done/
```

**When there is nothing to post (no content given):**

```
What would you like to post to LinkedIn?
Provide the post text or a topic to draft from.
```

**When content validation fails:**

```
Content validation failed:
- Content exceeds 3000 characters (current: 3412)
Please shorten the post and resubmit.
```

---

## Dependencies

Python files that must exist:
- `helpers/linkedin_poster.py` — browser automation via Playwright
- `helpers/dashboard_updater.py` — Dashboard activity and counter updates

Credentials required:
- `.credentials/linkedin_session/context.json` — Playwright storage state
  (created by running `watchers/linkedin_watcher.py` for the first interactive login)

Vault folders that must exist (created automatically if absent):
- `AI_Employee_Vault/Pending_Approval/`
- `AI_Employee_Vault/Approved/`
- `AI_Employee_Vault/Rejected/`
- `AI_Employee_Vault/Done/`

Log file (created automatically):
- `logs/linkedin_posts.log` — project root, not inside vault

---

## Notes

- **NEVER** call `post_to_linkedin()` before the user explicitly confirms approval.
  The HITL gate in Step 4 is security-critical and must not be bypassed.
- The poster retries once internally on network errors. If it returns `success: False`
  the skill should report the error verbatim and leave the file in `Approved/`.
- The skill must not log the full post content anywhere — only the first 50 characters
  in preview form, matching the log format used by `linkedin_poster.py`.
- If `helpers/linkedin_poster.py` is missing, report:
  "LinkedIn poster not installed. Ensure helpers/linkedin_poster.py exists."
- If the session file is missing, report:
  "LinkedIn session not found. Run the linkedin-monitor skill first to log in."
- If the session is expired, report:
  "LinkedIn session expired. Run the linkedin-monitor skill to re-authenticate."
- Image paths must be absolute or resolvable from the project root.
  Warn the user if a relative path is provided.
- Content flagged for extra review is not blocked — it is noted in the approval
  file so the human reviewer can make an informed decision.
