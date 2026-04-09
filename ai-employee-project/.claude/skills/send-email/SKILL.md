---
name: send-email
description: "Send emails via Gmail API with mandatory human approval before sending."
tier: silver
triggers:
  - "send email"
  - "send an email to"
  - "email to"
  - "draft email to"
  - "compose email"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  credentials_dir: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/.credentials"
  log_file: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/logs/email_sent.log"
  approval_expiry_hours: 24
---

# Skill: send-email

This skill collects email details from the user, creates a human-approval draft
file in `Pending_Approval/`, and only sends the email after a human explicitly
confirms approval. It calls `mcp_servers/email_server.py` for Gmail API delivery.
Auto-sending without approval is strictly forbidden.

---

## Purpose

- Prevent accidental or unauthorised outbound emails — every send requires an
  explicit human decision
- Support composing emails from natural language input, filling in missing fields
  by asking the user targeted questions
- Provide a clear, auditable trail: every email draft, send, and rejection is
  logged and reflected in the Dashboard
- Handle optional file attachments safely, verifying paths before any API call
- Keep credentials and email bodies out of logs (privacy and security)

---

## Process

### Step 1 — Collect email details

Extract fields from the user's message:

- **To** — look for an email address in the trigger phrase (e.g. "email to john@example.com")
- **Subject** — look for explicit subject wording; if absent, ask:
  > "What should the subject line be?"
- **Body** — look for body content after the address/subject; if absent, ask:
  > "What should the email say?"
- **Attachments** — if the user mentions a file, report, screenshot, or document,
  ask: "What is the file path for the attachment?"

Do not proceed to Step 2 until all three required fields (To, Subject, Body) are provided.

### Step 2 — Validate inputs

Check all of the following before creating any file:

- **To** — must contain `@` and a domain (e.g. `name@domain.com`); comma-separated
  addresses are each validated individually
- **Subject** — must not be empty
- **Body** — must not be empty
- **Attachments** — if provided, each path must look like a valid file path (not a
  URL); the actual existence check happens inside `email_server.py`

If any check fails, tell the user exactly what needs fixing and stop. Do not
create a draft file for invalid inputs.

### Step 3 — Create approval file

Call `mcp_servers/email_server.py` → `draft_email()` with the collected fields.
`draft_email()` creates `Pending_Approval/EMAIL_DRAFT_<timestamp>.md` automatically
and returns the file path.

After the file is created, tell the user:
> "Email draft created for approval.
> File: `Pending_Approval/EMAIL_DRAFT_<timestamp>.md`
> Review it and move to `Approved/` to send, or `Rejected/` to cancel."

Update the Dashboard: increment Pending Approvals counter and add an activity entry.

### Step 4 — Show preview

Display a summary so the user can confirm they are approving the right email:

```
Email ready for approval:
  To:          <recipient(s)>
  Subject:     <subject>
  Preview:     <first 100 characters of body>…
  Attachments: <count, or None>

Move the file to Approved/ to send, or Rejected/ to cancel.
Say 'approved' or 'rejected' to proceed.
```

### Step 5 — Wait for human approval (HITL gate)

Ask the user:
> "Have you reviewed and approved the email? Reply 'approved' to send or 'rejected' to cancel."

**Do not call `send_email()` until the user explicitly confirms.**
This gate is security-critical and must never be bypassed.

### Step 6a — On approval

Read the To, Subject, Body, and Attachments from the approved file in `Approved/`.

Call `mcp_servers/email_server.py` → `send_email()` with those values (see How to Run).

**On success:**
- The log file entry is written by `email_server.py`:
  `[timestamp] [SUCCESS] To: <addr> | Subject: <subject>`
- Update Dashboard: decrement Pending Approvals, increment Emails Sent, add activity entry
- Move the approval file from `Approved/` to `Done/`
- Report to the user:
  > "Email sent successfully!
  > Message ID: <message_id>
  > Sent to: <recipient>
  > Timestamp: <timestamp>"

**On failure:**
- The log file entry is written by `email_server.py`:
  `[timestamp] [FAILED] To: <addr> | Subject: <subject> | error: <message>`
- Update Dashboard: note failure in activity log
- Leave the approval file in `Approved/` so the user can retry
- Report to the user:
  > "Email failed: <error message>
  > The approval file remains in Approved/ — say 'retry send email' to try again."

### Step 6b — On rejection

- Move the approval file from `Pending_Approval/` (or wherever it is) to `Rejected/`
- Update Dashboard: decrement Pending Approvals, increment Emails Rejected, add activity entry
- Report to the user:
  > "Email cancelled. Draft archived in Rejected/."

### Step 7 — Expiry

If 24 hours pass with no decision, the draft is auto-rejected:
- Move from `Pending_Approval/` to `Rejected/` with reason "Approval timeout — 24 hours elapsed"
- Update Dashboard
- Do not send the email

---

## How to Run

Two functions in `mcp_servers/email_server.py` are used — first `draft_email()`
to create the approval file, then `send_email()` after confirmation.

```
Module:   mcp_servers.email_server

Function 1 — create approval file (Step 3):
  draft_email(to, subject, body, attachments, vault_path)
  Arguments:
    to          — recipient address(es), comma-separated string
    subject     — email subject line
    body        — email body text or HTML
    attachments — list of file path strings, or None
    vault_path  — from config.vault_path
  Returns: str — absolute path of the created EMAIL_DRAFT_<timestamp>.md file

Function 2 — send email (Step 6a, after approval only):
  send_email(to, subject, body, attachments, vault_path, credentials_dir)
  Arguments:
    to              — same recipient string as above
    subject         — same subject as above
    body            — same body as above
    attachments     — same attachments list as above, or None
    vault_path      — from config.vault_path
    credentials_dir — from config.credentials_dir
  Returns dict:
    success     (bool)
    message_id  (str | None)
    sent_to     (str)
    timestamp   (str, ISO UTC)
    error       (str | None)
```

Error strings returned by `send_email()`:
- `"Gmail credentials not found: …"` → credentials.json missing, user must authorise
- `"Invalid email address: …"`        → bad recipient format
- `"Attachment file not found: …"`    → file does not exist on disk
- `"Gmail API error 429: …"`          → rate limited
- Any other string                    → surface verbatim to user

---

## Output — Vault Card Format

Approval file written to `Pending_Approval/`:

```yaml
---
action_type: send_email
created: 2026-04-09T16:00:00
expires: 2026-04-10T16:00:00
status: pending
priority: normal
sent_to: "recipient@example.com"
subject: "Email subject line"
---
```

The file body includes `## Email Details`, `## Email Body`, `## Attachments`,
`## To Approve`, `## To Reject`, `## Rejection Reason`, and `## Auto-Reject` sections.

No separate vault card is created for the send result — the approval file itself
(moved to `Done/` or `Rejected/`) serves as the permanent record.

### Priority rules

All email drafts use `priority: normal` by default.
If the subject or body contains `urgent`, `asap`, `invoice`, or `payment`,
note it in the preview shown to the user, but do not change the frontmatter
priority — that is a human decision made during review.

---

## Expected Output

**Email submitted for approval:**

```
Email draft created for approval.
File: Pending_Approval/EMAIL_DRAFT_20260409_160000.md

Email ready for approval:
  To:          john@example.com
  Subject:     Project Update Q2
  Preview:     Hi John, I wanted to share a quick update on the Q2 project milestones…
  Attachments: None

Move the file to Approved/ to send, or Rejected/ to cancel.
Say 'approved' or 'rejected' to proceed.
```

**Email sent successfully:**

```
Email sent successfully!
  Message ID: 18f3c2a1d4e5b7f9
  Sent to:    john@example.com
  Timestamp:  2026-04-09T16:02:15
Approval file moved to Done/
```

**Email rejected by user:**

```
Email cancelled. Draft archived in Rejected/.
```

**Validation failure (bad address):**

```
Invalid email address format: "john at example dot com"
Please provide a valid address (e.g. john@example.com) and try again.
```

**Credentials missing:**

```
Gmail credentials not found.
Run gmail_watcher.py first to authorise with Google:
  python watchers/gmail_watcher.py
```

---

## Dependencies

Python files that must exist:
- `mcp_servers/email_server.py` — `send_email()` and `draft_email()` functions
- `helpers/dashboard_updater.py` — Dashboard activity and counter updates

Credentials required:
- `.credentials/credentials.json` — Google OAuth2 client credentials
  (downloaded from Google Cloud Console → APIs & Services → Credentials)
- `.credentials/token.json` — OAuth2 token with `gmail.send` scope
  (created automatically by `email_server.py` on first run)
  If the existing token only has `gmail.readonly`, delete `token.json`
  and re-run — the browser flow will request both scopes

Vault folders that must exist (created automatically if absent):
- `AI_Employee_Vault/Pending_Approval/`
- `AI_Employee_Vault/Approved/`
- `AI_Employee_Vault/Rejected/`
- `AI_Employee_Vault/Done/`

Log file (created automatically by `email_server.py`):
- `logs/email_sent.log` — project root, never inside vault
  Format: `[timestamp] [SUCCESS/FAILED] To: addr | Subject: subject`
  Email body is never written to this file

---

## Notes

- **NEVER** call `send_email()` before the user explicitly confirms approval.
  The HITL gate in Step 5 is security-critical and must not be bypassed.
- Email body content is never logged anywhere — only To and Subject appear in
  `logs/email_sent.log`. This is a privacy requirement.
- `draft_email()` handles file creation and collision avoidance (appends a counter
  if two drafts are created in the same second).
- `send_email()` validates the recipient address internally and will return an
  error dict rather than raise an exception — always check `result["success"]`.
- Token refresh is automatic inside `email_server.py`; if refresh fails (network
  error), the error string will contain "network error" — advise the user to
  check their internet connection and retry.
- For multiple recipients, pass a comma-separated string: `"a@x.com, b@y.com"`.
  Each address is validated individually inside `email_server.py`.
- If the user wants to resend a rejected email, they must trigger the skill again
  from scratch — rejected files are archived and not reused.
- HTML bodies are auto-detected by `email_server.py` (if body starts with `<`).
  Plain text is used otherwise. The skill does not need to specify this.
