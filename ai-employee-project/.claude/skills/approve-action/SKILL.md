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
  approval_expiry_hours: 24
---

# Skill: approve-action

This skill lists all pending approvals in `Pending_Approval/`, lets the user
select one (or all) to review, moves approved files to `Approved/` with updated
frontmatter, triggers execution of the approved action, and moves the final file
to `Done/`. Every decision is logged and reflected in the Dashboard.
Auto-execution without explicit human confirmation is strictly forbidden.

---

## Purpose

- Provide a single entry point for reviewing and acting on any pending action —
  emails, LinkedIn posts, or any future action type added to the vault
- Enforce Human-in-the-Loop (HITL) by requiring an explicit human selection before
  any outbound action is triggered
- Give the user a clear numbered list so nothing pending is accidentally missed
- Update the approval file's frontmatter at each stage (approved, executed) so the
  file itself is a full audit trail of what happened and when
- Write structured log entries to `logs/approvals.log` covering both the approval
  decision and the execution result

---

## Process

### Step 1 — Check Pending_Approval/ folder

Scan `AI_Employee_Vault/Pending_Approval/` for all `.md` files.

If the folder does not exist, create it silently and continue.

If no `.md` files are found, tell the user:

```
No pending approvals found.
All actions have been reviewed or no actions are awaiting approval.
```

Then stop.

---

### Step 2 — List all pending approvals

For each file found, parse its YAML frontmatter and extract:
- `action_type` — e.g. `send_email`, `linkedin_post`
- `created` — ISO timestamp when the draft was submitted
- `expires` — ISO timestamp when the approval auto-expires

Compute a human-readable age from `created` (e.g. "2 hours ago", "5 hours ago").
Compute time remaining from `expires` (e.g. "expires in 18 hours").

Mark any file where `expires` is already in the past with `[EXPIRED]`.

Build a preview label per action type:
- `send_email`: show `To: <sent_to>` and truncated subject
- `linkedin_post`: show first 50 characters of the `## Post Content` section body
- Unknown types: show the raw `action_type` value

Display the numbered list:

```
Pending Approvals (3 item(s)):

  [1] send_email    — To: client@example.com | Subject: Q2 Update
        Created: 2 hours ago  |  Expires in: 22 hours
        File: EMAIL_DRAFT_20260409_140000.md

  [2] linkedin_post — "We are thrilled to announce our Q2 results…"
        Created: 5 hours ago  |  Expires in: 19 hours
        File: LINKEDIN_POST_20260409_110000.md

  [3] send_email    — To: team@company.com | Subject: Meeting Reschedule
        Created: 6 hours ago  |  Expires in: 18 hours
        File: EMAIL_DRAFT_20260409_100000.md
```

Then prompt:
> "Which action would you like to approve? Enter a number, a filename, or 'all' to approve everything."

---

### Step 3 — User selects action to approve

Accept any of the following selection formats:

- **By number** — `1`, `#1`, `approve 1`, `approve #1`
- **By filename** — `EMAIL_DRAFT_20260409_140000.md` or a unique fragment of the filename
- **Approve all** — `all`, `approve all`

For "approve all", collect all non-expired files and process them sequentially through
Steps 4–8 for each file. After all are processed, report a combined summary.

If the identifier is ambiguous (matches multiple files), re-list the matching files
and ask the user to be more specific.

If no match is found, report "Invalid approval number/file" and re-display the list.

---

### Step 4 — Validate approval

Before moving any file, verify:

1. **File exists** in `Pending_Approval/` — if not, report "Approval file not found" and refresh the list.
2. **Not expired** — if the current time is past `expires`, report:
   > "Cannot approve: expired (created <age>). This action can no longer be executed."
   Move the file to `Rejected/` with reason "Approval timeout — 24 hours elapsed" and stop.
3. **action_type is present** — if missing or unrecognised, warn the user but allow them to proceed (execution will be skipped for unknown types).

---

### Step 5 — Move to Approved/ and update frontmatter

Move the file from `Pending_Approval/` to `Approved/`.

Update the file's YAML frontmatter in place by adding or overwriting these fields:

```yaml
status: approved
approved_by: human
approved_at: <current ISO timestamp>
```

Example frontmatter after this step:

```yaml
---
action_type: send_email
created: 2026-04-09T14:00:00
expires: 2026-04-10T14:00:00
status: approved
approved_by: human
approved_at: 2026-04-09T16:30:00
---
```

---

### Step 6 — Execute action based on type

Dispatch to the correct helper based on `action_type`:

**`send_email`**
- Read `sent_to`, `subject`, body (from `## Email Body` section), and attachments (from `## Attachments` section) from the approved file
- Call `mcp_servers/email_server.py` → `send_email()` with those values plus `vault_path` and `credentials_dir`
- Capture the returned result dict

**`linkedin_post`**
- Read `content` (from `## Post Content` section) and `image_path` (from `## Image` section, or None) from the approved file
- Call `helpers/linkedin_poster.py` → `post_to_linkedin()` with those values plus `vault_path` and `session_dir`
- Capture the returned result dict

**Unknown action type**
- Do not attempt execution
- Set result to: `{ success: false, error: "Unknown action type: <type>" }`
- Warn the user that execution was skipped and the file will remain in `Approved/`

---

### Step 7 — Handle execution result

**If SUCCESS:**

Update the file's YAML frontmatter with:

```yaml
executed: true
executed_at: <current ISO timestamp>
execution_result: success
```

Move the file from `Approved/` to `Done/`.

Append two entries to `logs/approvals.log`:

```
[2026-04-09 16:30:00] APPROVED | EMAIL_DRAFT_20260409_140000.md | Approved by: human
[2026-04-09 16:30:05] EXECUTED | send_email | To: client@example.com | Result: success
```

For LinkedIn posts, the second line uses:
```
[2026-04-09 16:30:05] EXECUTED | linkedin_post | URL: <post_url> | Result: success
```

Report to the user:

- Email: `"Email sent successfully to <addr>. Message ID: <id>. File moved to Done/."`
- LinkedIn: `"Post published successfully. URL: <url>. File moved to Done/."`

**If FAILED:**

Update the file's YAML frontmatter with:

```yaml
executed: true
executed_at: <current ISO timestamp>
execution_result: failed
execution_error: "<error message>"
```

Leave the file in `Approved/` so the user can retry.

Append two entries to `logs/approvals.log`:

```
[2026-04-09 16:30:00] APPROVED | EMAIL_DRAFT_20260409_140000.md | Approved by: human
[2026-04-09 16:30:05] EXECUTED | send_email | To: client@example.com | Result: failed | Error: <error>
```

Report to the user:

> "Execution failed: <error message>.
> The file remains in Approved/ for retry.
> Say 'retry send email' or 'retry linkedin post' to try again."

---

### Step 8 — Update Dashboard

Call `helpers/dashboard_updater.py` after every approval (success or failure):

- Decrement `Pending Approvals` counter (stat: `tasks_in_needs_action` or equivalent)
- Increment `Actions Approved` counter
- Add activity entry:
  - On success: `"Approved and executed: <action_type> — <brief description>"`
  - On failure: `"Approved but execution failed: <action_type> — <error summary>"`

---

### Step 9 — Clean up and report

After a single approval, report the summary:

```
Approved: EMAIL_DRAFT_20260409_140000.md
Execution: success
Email sent to: client@example.com
File moved to: Done/
Dashboard updated.
```

After "approve all", report a table summary:

```
Approval Summary (3 processed):
  [1] EMAIL_DRAFT_20260409_140000.md  → send_email    → success
  [2] LINKEDIN_POST_20260409_110000.md → linkedin_post → success
  [3] EMAIL_DRAFT_20260409_100000.md  → send_email    → failed (Gmail API error 429)

2 succeeded, 1 failed. Failed files remain in Approved/ for retry.
Dashboard updated.
```

---

## How to Run

Two different modules are dispatched depending on `action_type` read from the
approved file's frontmatter. Always read `action_type` before calling either module.

```
Module 1: mcp_servers.email_server   (action_type = send_email)
Function: send_email(to, subject, body, attachments, vault_path, credentials_dir)
Arguments:
  to              — recipient address(es) from approved file frontmatter (sent_to)
  subject         — subject line from approved file frontmatter
  body            — email body text from ## Email Body section of approved file
  attachments     — list of paths from ## Attachments section, or None
  vault_path      — from config.vault_path
  credentials_dir — from config.credentials_dir
Returns dict:
  success     (bool)
  message_id  (str | None)
  sent_to     (str)
  timestamp   (str, ISO UTC)
  error       (str | None)

Module 2: helpers.linkedin_poster   (action_type = linkedin_post)
Function: post_to_linkedin(content, image_path, vault_path, session_dir)
Arguments:
  content      — full post text from ## Post Content section of approved file
  image_path   — path from ## Image section of approved file, or None
  vault_path   — from config.vault_path
  session_dir  — config.credentials_dir + "/linkedin_session"
Returns dict:
  success    (bool)
  post_url   (str | None)
  post_id    (str | None)
  timestamp  (str, ISO UTC)
  error      (str | None)

Dashboard updates: helpers.dashboard_updater
  update_activity(vault_path, message)
  update_stats(vault_path, stat_name, value, operation)
```

---

## Output — Vault Card Format

No new vault card is created. The existing approval file is updated in place and
moved between folders to reflect the current state.

**Full frontmatter lifecycle of an approval file:**

```yaml
---
action_type: send_email
created: 2026-04-09T14:00:00
expires: 2026-04-10T14:00:00
status: approved
approved_by: human
approved_at: 2026-04-09T16:30:00
executed: true
executed_at: 2026-04-09T16:30:05
execution_result: success
---
```

For a failed execution:

```yaml
---
action_type: send_email
created: 2026-04-09T14:00:00
expires: 2026-04-10T14:00:00
status: approved
approved_by: human
approved_at: 2026-04-09T16:30:00
executed: true
executed_at: 2026-04-09T16:30:05
execution_result: failed
execution_error: "Gmail API error 429: rate limited"
---
```

**Log format — two entries per action (logs/approvals.log):**

```
[2026-04-09 16:30:00] APPROVED | EMAIL_DRAFT_20260409_140000.md | Approved by: human
[2026-04-09 16:30:05] EXECUTED | send_email | To: client@example.com | Result: success
```

```
[2026-04-09 16:31:00] APPROVED | LINKEDIN_POST_20260409_110000.md | Approved by: human
[2026-04-09 16:31:03] EXECUTED | linkedin_post | URL: https://linkedin.com/... | Result: success
```

Email body content and full LinkedIn post text are never written to any log file.

---

## Expected Output

**Example 1 — "review approvals" (list only):**

```
Pending Approvals (3 item(s)):

  [1] send_email    — To: client@example.com | Subject: Q2 Update
        Created: 2 hours ago  |  Expires in: 22 hours
        File: EMAIL_DRAFT_20260409_140000.md

  [2] linkedin_post — "We are thrilled to announce our Q2 results…"
        Created: 5 hours ago  |  Expires in: 19 hours
        File: LINKEDIN_POST_20260409_110000.md

  [3] send_email    — To: team@company.com | Subject: Meeting Reschedule
        Created: 6 hours ago  |  Expires in: 18 hours
        File: EMAIL_DRAFT_20260409_100000.md

Which action would you like to approve? Enter a number, filename, or 'all'.
```

**Example 2 — "approve #1" (email):**

```
Email sent successfully to client@example.com.
  Message ID: 18f3c2a1d4e5b7f9
  Timestamp:  2026-04-09T16:30:05
File moved to Done/.
Dashboard updated.
```

**Example 3 — "approve the LinkedIn post":**

```
Post published successfully.
  URL: https://www.linkedin.com/feed/update/urn:li:activity:1234567890
  Posted at: 2026-04-09T16:31:03
File moved to Done/.
Dashboard updated.
```

**Example 4 — "approve all":**

```
Approval Summary (3 processed):
  [1] EMAIL_DRAFT_20260409_140000.md   → send_email    → success
  [2] LINKEDIN_POST_20260409_110000.md → linkedin_post → success
  [3] EMAIL_DRAFT_20260409_100000.md   → send_email    → failed (Gmail API error 429)

2 succeeded, 1 failed. Failed files remain in Approved/ for retry.
Dashboard updated.
```

**Example 5 — no pending approvals:**

```
No pending approvals found.
All actions have been reviewed or no actions are awaiting approval.
```

**Example 6 — expired approval:**

```
Cannot approve: expired (created 25 hours ago).
This action can no longer be executed.
File moved to Rejected/ with reason: "Approval timeout — 24 hours elapsed".
```

**Example 7 — invalid selection:**

```
Invalid approval number/file: "5"
Please choose from the list above (1–3) or enter a valid filename.
```

---

## Dependencies

Python files that must exist:
- `mcp_servers/email_server.py` — `send_email()` for dispatching approved emails
- `helpers/linkedin_poster.py` — `post_to_linkedin()` for dispatching approved posts
- `helpers/dashboard_updater.py` — Dashboard activity and counter updates

Credentials required (email dispatch):
- `.credentials/credentials.json` — Google OAuth2 client credentials
- `.credentials/token.json` — OAuth2 token with `gmail.send` scope
  (delete and re-run watcher if existing token only has `gmail.readonly`)

Credentials required (LinkedIn dispatch):
- `.credentials/linkedin_session/context.json` — Playwright session storage state
  (created by `watchers/linkedin_watcher.py` on first interactive login)

Vault folders (created automatically if absent):
- `AI_Employee_Vault/Pending_Approval/`
- `AI_Employee_Vault/Approved/`
- `AI_Employee_Vault/Rejected/`
- `AI_Employee_Vault/Done/`

Log files (created automatically if absent):
- `logs/approvals.log` — one APPROVED + one EXECUTED entry per action
- `logs/email_sent.log` — updated by `email_server.py` on successful send
- `logs/linkedin_posts.log` — updated by `linkedin_poster.py` on successful post

---

## Notes

- **NEVER** call `send_email()` or `post_to_linkedin()` without an explicit human
  selection in Step 3. The approval gate must not be bypassed under any circumstance.
- Only a human can approve — `approved_by` is always set to `human`. There is no
  code path that sets this to anything else.
- Expired approvals (`expires` in the past) must be moved to `Rejected/` and must
  not be executed, even if the user explicitly tries to approve them.
- When processing "approve all", skip expired files and report them separately in
  the summary as `[EXPIRED — auto-rejected]`.
- If a file is missing from `Pending_Approval/` when the user tries to approve it
  (e.g. moved by another process), report "Approval file not found" and refresh the list.
- Frontmatter must be updated before calling the execution helper so the file
  reflects `status: approved` even if execution subsequently fails.
- Email body content and full LinkedIn post text are never written to any log file.
  Only `To` + `Subject` (email) or the first 50 characters (LinkedIn) appear in logs.
- If `mcp_servers/email_server.py` is missing when approving an email action, report:
  "Email server not installed. Ensure mcp_servers/email_server.py exists."
- If `helpers/linkedin_poster.py` is missing when approving a LinkedIn post, report:
  "LinkedIn poster not installed. Ensure helpers/linkedin_poster.py exists."
- If the LinkedIn session is expired, report:
  "LinkedIn session expired. Run the linkedin-monitor skill to re-authenticate."
- For unknown `action_type` values, the file is moved to `Approved/` and frontmatter
  is updated, but execution is skipped. The user must handle the action manually.
- `logs/approvals.log` is separate from `logs/email_sent.log` and
  `logs/linkedin_posts.log`. All three are updated on a successful send/post.
