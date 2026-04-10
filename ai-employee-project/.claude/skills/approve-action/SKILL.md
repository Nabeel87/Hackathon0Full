---
name: approve-action
description: "Approve pending actions (emails, LinkedIn posts, etc.) and trigger execution"
tier: silver
triggers:
  - "approve"
  - "approve action"
  - "approve pending"
  - "review approvals"
  - "approve email"
  - "approve post"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  credentials_dir: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/.credentials"
  log_file: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/logs/approvals.log"
---

# Skill: approve-action

This skill lists all pending approvals in `Pending_Approval/`, lets the user
select one to review, moves the approved file to `Approved/`, then triggers
execution of that action (email send or LinkedIn post). Every approval is logged
and reflected in the Dashboard. Auto-execution without explicit human confirmation
is strictly forbidden.

---

## Purpose

- Provide a single entry point for reviewing and acting on any pending action —
  emails, LinkedIn posts, or any future action type
- Enforce Human-in-the-Loop (HITL) by requiring explicit confirmation before any
  outbound action is triggered
- Give the user a clear numbered list of what is waiting so nothing is missed
- Create an auditable log entry in `logs/approvals.log` for every approval or rejection
- Keep the Dashboard accurate by updating activity and counters after every decision

---

## Process

### Step 1 — List pending approvals

Scan `AI_Employee_Vault/Pending_Approval/` for all `.md` files.

For each file found, read its YAML frontmatter and extract:
- `action_type` — e.g. `send_email`, `linkedin_post`
- `created` — ISO timestamp of when the draft was created
- `expires` — ISO timestamp of when the approval will auto-expire
- Any preview fields relevant to the action type:
  - For `send_email`: `sent_to` and `subject`
  - For `linkedin_post`: first 60 characters of the `## Post Content` section body

Display a numbered list:

```
Pending Approvals (N item(s)):

  [1] send_email     — To: john@example.com | Subject: Q2 Update
        Created: 2026-04-09 16:00  |  Expires: 2026-04-10 16:00
        File: EMAIL_DRAFT_20260409_160000.md

  [2] linkedin_post  — "We are thrilled to announce our Q2 results…"
        Created: 2026-04-09 15:45  |  Expires: 2026-04-10 15:45
        File: LINKEDIN_POST_20260409_154500.md
```

If `Pending_Approval/` is empty, tell the user:

```
No pending approvals found.
All actions have been reviewed or no actions are awaiting approval.
```

Then stop — there is nothing to approve.

### Step 2 — Select an action

If the user's trigger phrase already contains an identifier (filename fragment or
list number, e.g. "approve 1" or "approve EMAIL_DRAFT_20260409"), use that to
pre-select without asking.

Otherwise ask:
> "Which action would you like to approve? Enter the number from the list above,
> or the filename."

Wait for the user's response before continuing.

Resolve the selection to a full filename. If the identifier is ambiguous (matches
more than one file), list the matching files and ask the user to be more specific.
If no match is found, tell the user and re-display the list.

### Step 3 — Show full preview

Read the full content of the selected file and display a detailed preview so the
user can make an informed decision:

**For `send_email`:**
```
Action:      Send Email
To:          <recipient(s)>
Subject:     <subject>
Body:        <full email body>
Attachments: <list of paths, or None>
Created:     <timestamp>
Expires:     <timestamp>
File:        <filename>
```

**For `linkedin_post`:**
```
Action:      LinkedIn Post
Content:     <full post text>
Image:       <image path, or None>
Created:     <timestamp>
Expires:     <timestamp>
File:        <filename>
```

**For unknown action types:**
Display the full raw markdown content of the file and note the action type.

After displaying the preview, ask:
> "Approve this action? Reply 'yes' / 'approve' to execute, or 'no' / 'reject' to cancel."

Do not execute anything until the user responds. This is the HITL gate.

### Step 4a — On approval

1. Move the file from `Pending_Approval/` to `Approved/`.

2. Append a log entry to `logs/approvals.log`:
   ```
   [<ISO timestamp>] [APPROVED] <action_type> | File: <filename> | Approved by: human
   ```
   Create `logs/approvals.log` if it does not exist.

3. Dispatch execution based on `action_type`:

   **`send_email`** — call `mcp_servers/email_server.py` → `send_email()`:
   - Read `sent_to`, `subject`, body, and attachments from the approved file
   - Call with: `to`, `subject`, `body`, `attachments`, `vault_path`, `credentials_dir`
   - On success:
     - Log `[<timestamp>] [SENT] To: <addr> | Subject: <subject>` to `logs/email_sent.log`
     - Move the file from `Approved/` to `Done/`
     - Report: "Email sent successfully! Message ID: <id> | Sent to: <addr>"
   - On failure:
     - Leave the file in `Approved/` so the user can retry
     - Report: "Email send failed: <error>. File remains in Approved/ — say 'retry send email' to try again."

   **`linkedin_post`** — call `helpers/linkedin_poster.py` → `post_to_linkedin()`:
   - Read `content` and `image_path` from the approved file
   - Call with: `content`, `image_path`, `vault_path`, `session_dir`
   - On success:
     - Log `[<timestamp>] [SUCCESS] <first 50 chars>… | URL: <url>` to `logs/linkedin_posts.log`
     - Move the file from `Approved/` to `Done/`
     - Report: "Posted to LinkedIn successfully! URL: <url> | Posted at: <timestamp>"
   - On failure:
     - Leave the file in `Approved/` for retry
     - Report: "LinkedIn post failed: <error>. File remains in Approved/ — say 'retry linkedin post' to try again."

   **Unknown action type** — do not attempt execution. Report:
   > "Unknown action type '<type>'. File moved to Approved/ but execution was not triggered.
   > Handle this action manually or implement a handler for this action type."

4. Update Dashboard:
   - Decrement Pending Approvals counter
   - Increment Actions Approved counter
   - Add activity entry: `"Action approved and executed: <action_type> — <brief description>"`

### Step 4b — On rejection

1. Move the file from `Pending_Approval/` to `Rejected/`.

2. Ask the user (optional):
   > "Rejection reason? Press Enter to skip or type a reason."
   If a reason is provided, append it to the `## Rejection Reason` section of the
   file in `Rejected/`.

3. Append a log entry to `logs/approvals.log`:
   ```
   [<ISO timestamp>] [REJECTED] <action_type> | File: <filename> | Reason: <reason or "none">
   ```

4. Update Dashboard:
   - Decrement Pending Approvals counter
   - Increment Actions Rejected counter
   - Add activity entry: `"Action rejected: <action_type> — <filename>"`

5. Report to the user:
   > "Action rejected and archived in Rejected/."

---

## How to Run

Two different modules are dispatched depending on the `action_type` in the
approved file's frontmatter. Read `action_type` before calling either module.

```
Module 1: mcp_servers.email_server   (for action_type = send_email)
Function: send_email(to, subject, body, attachments, vault_path, credentials_dir)
Arguments:
  to              — recipient address(es), comma-separated string from approved file
  subject         — subject line from approved file
  body            — email body from approved file (## Email Body section)
  attachments     — list of paths from approved file, or None
  vault_path      — from config.vault_path
  credentials_dir — from config.credentials_dir
Returns dict:
  success     (bool)
  message_id  (str | None)
  sent_to     (str)
  timestamp   (str, ISO UTC)
  error       (str | None)

Module 2: helpers.linkedin_poster   (for action_type = linkedin_post)
Function: post_to_linkedin(content, image_path, vault_path, session_dir)
Arguments:
  content      — full post text from approved file (## Post Content section)
  image_path   — image path from approved file (## Image section), or None
  vault_path   — from config.vault_path
  session_dir  — from config.credentials_dir + "/linkedin_session"
Returns dict:
  success    (bool)
  post_url   (str | None)
  post_id    (str | None)
  timestamp  (str, ISO UTC)
  error      (str | None)
```

---

## Output — Vault Card Format

No new vault card is created by this skill. The existing approval file is moved
between folders (`Pending_Approval/` → `Approved/` → `Done/` or `Rejected/`) to
reflect the current state.

Log entries are appended to `logs/approvals.log` (created if absent):

```
[2026-04-09T16:05:00] [APPROVED] send_email | File: EMAIL_DRAFT_20260409_160000.md | Approved by: human
[2026-04-09T16:10:00] [REJECTED] linkedin_post | File: LINKEDIN_POST_20260409_154500.md | Reason: needs revision
```

---

## Expected Output

**When pending approvals exist:**

```
Pending Approvals (2 item(s)):

  [1] send_email     — To: john@example.com | Subject: Q2 Update
        Created: 2026-04-09 16:00  |  Expires: 2026-04-10 16:00
        File: EMAIL_DRAFT_20260409_160000.md

  [2] linkedin_post  — "We are thrilled to announce our Q2 results…"
        Created: 2026-04-09 15:45  |  Expires: 2026-04-10 15:45
        File: LINKEDIN_POST_20260409_154500.md

Which action would you like to approve? Enter the number or filename.
```

**After user selects and approves item 1:**

```
Email sent successfully!
  Message ID: 18f3c2a1d4e5b7f9
  Sent to:    john@example.com
  Timestamp:  2026-04-09T16:07:15
Approval logged. File moved to Done/.
Dashboard updated.
```

**When nothing is pending:**

```
No pending approvals found.
All actions have been reviewed or no actions are awaiting approval.
```

**After rejection:**

```
Action rejected and archived in Rejected/.
```

---

## Dependencies

Python files that must exist:
- `mcp_servers/email_server.py` — `send_email()` for dispatching approved emails
- `helpers/linkedin_poster.py` — `post_to_linkedin()` for dispatching approved posts
- `helpers/dashboard_updater.py` — Dashboard activity and counter updates

Credentials required (for email dispatch):
- `.credentials/credentials.json` — Google OAuth2 client credentials
- `.credentials/token.json` — OAuth2 token with `gmail.send` scope

Credentials required (for LinkedIn dispatch):
- `.credentials/linkedin_session/context.json` — Playwright session storage state

Vault folders that must exist (created automatically if absent):
- `AI_Employee_Vault/Pending_Approval/`
- `AI_Employee_Vault/Approved/`
- `AI_Employee_Vault/Rejected/`
- `AI_Employee_Vault/Done/`

Log files (created automatically if absent):
- `logs/approvals.log` — one entry per approval or rejection decision
- `logs/email_sent.log` — updated on successful email send
- `logs/linkedin_posts.log` — updated on successful LinkedIn post

---

## Notes

- **NEVER** call `send_email()` or `post_to_linkedin()` before the user explicitly
  confirms in Step 4. The HITL gate must not be bypassed under any circumstance.
- If `Pending_Approval/` does not exist, create it silently and report no pending items.
- Expired files (where `expires` is in the past) should be flagged in the list with
  `[EXPIRED]` next to the timestamp so the user can choose to reject them explicitly.
  Do not auto-reject during this skill — let the user decide.
- If the approved file has already been moved (e.g. by another process) and is not
  found in `Pending_Approval/`, report the missing file and refresh the list.
- For files with unknown or missing `action_type`, display them in the list with
  type `unknown` and allow the user to reject them; do not attempt execution.
- The skill reads body content from the approval file's markdown sections, not from
  frontmatter. Parse the `## Email Body` or `## Post Content` section accordingly.
- Email body content is never written to `logs/approvals.log` — only `To` and
  `Subject` for emails, and the first 50 characters for LinkedIn posts. This is a
  privacy requirement.
- If `mcp_servers/email_server.py` is missing when approving an email, report:
  "Email server not installed. Ensure mcp_servers/email_server.py exists."
- If `helpers/linkedin_poster.py` is missing when approving a LinkedIn post, report:
  "LinkedIn poster not installed. Ensure helpers/linkedin_poster.py exists."
- If the LinkedIn session is expired, report:
  "LinkedIn session expired. Run the linkedin-monitor skill to re-authenticate."
