---
name: reject-action
description: "Reject pending actions with reason and archive for audit trail"
tier: silver
triggers:
  - "reject"
  - "reject action"
  - "reject pending"
  - "decline approval"
  - "cancel action"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  log_file: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/logs/approvals.log"
  approval_expiry_hours: 24
---

# Skill: reject-action

This skill lists all pending approvals in `Pending_Approval/`, lets the user
select one (or all) to reject, prompts for a mandatory rejection reason, updates
the file's frontmatter, appends a rejection details section, moves the file to
`Rejected/`, and logs the decision in `logs/approvals.log`. The rejected action
is never executed under any circumstances.

---

## Purpose

- Provide a safe, auditable path for declining any pending action — emails,
  LinkedIn posts, or any future action type
- Require a human-supplied rejection reason so every decision is documented and
  can inform future resubmissions
- Archive rejected files in `Rejected/` permanently so the full history is
  available for review and learning
- Distinguish manual human rejections (`rejected_by: human`) from system timeouts
  (`rejected_by: system`) so the audit log is unambiguous
- Keep the Dashboard accurate by updating counters and activity after every rejection

---

## Process

### Step 1 — Check Pending_Approval/ folder

Scan `AI_Employee_Vault/Pending_Approval/` for all `.md` files.

If the folder does not exist, create it silently and continue.

If no `.md` files are found, tell the user:

```
No pending approvals found.
There are no actions waiting for a decision.
```

Then stop.

---

### Step 2 — List all pending approvals

For each file found, parse its YAML frontmatter and extract:
- `action_type` — e.g. `send_email`, `linkedin_post`
- `created` — ISO timestamp when the draft was submitted
- `expires` — ISO timestamp when the approval auto-expires

Compute a human-readable age from `created` (e.g. "2 hours ago").
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

  [3] send_email    — To: team@company.com | Subject: Meeting Reschedule  [EXPIRED]
        Created: 25 hours ago  |  Expired: 1 hour ago
        File: EMAIL_DRAFT_20260408_150000.md
```

Then prompt:
> "Which action would you like to reject? Enter a number, a filename, or 'all' to reject everything."

---

### Step 3 — User selects action to reject

Accept any of the following selection formats:

- **By number** — `2`, `#2`, `reject 2`, `reject #2`
- **By filename** — `LINKEDIN_POST_20260409_110000.md` or a unique fragment
- **Reject all** — `all`, `reject all`

For "reject all", collect all files (including expired) and process them
sequentially through Steps 4–9, applying the same reason to every file.

If the identifier is ambiguous (matches more than one file), re-list the matches
and ask the user to be more specific.

If no match is found, report "Invalid action number/file" and re-display the list.

---

### Step 4 — Prompt for rejection reason

After the user selects an action, show a brief preview of the selected item and ask:

> "Why are you rejecting this action?"

Wait for the user's response. A reason is **required** — do not proceed with an
empty reason. If the user submits a blank response, ask again:

> "A rejection reason is required for the audit trail. Please provide a reason."

**For "reject all"**, ask once before processing any file:
> "Why are you rejecting all pending actions? This reason will apply to each."

Common reason examples (do not suggest unless asked):
- "Email tone inappropriate for client relationship"
- "Wrong recipient address"
- "Content needs revision before sending"
- "Strategy changed, no longer needed"
- "Timing not right, resubmit next week"
- "Missing key information"
- "Requires legal review first"
- "Better to handle this via phone call"

---

### Step 5 — Validate rejection

Before moving any file, verify:

1. **File exists** in `Pending_Approval/` — if not, report "Approval file not found" and refresh the list.
2. **Reason is not empty** — already enforced in Step 4; re-confirm before file operations.

Note: expired files **can** be manually rejected (unlike approval, which blocks
expired items). The user may still want to formally reject and log an expired draft.
The `[EXPIRED]` label in the list is informational, not a blocker for rejection.

---

### Step 6 — Move to Rejected/ and update frontmatter

Move the file from `Pending_Approval/` to `Rejected/`.

Update the file's YAML frontmatter in place by adding or overwriting these fields:

```yaml
status: rejected
rejected_by: human
rejected_at: <current ISO timestamp>
rejection_reason: "<user's reason>"
```

Example frontmatter after this step:

```yaml
---
action_type: send_email
created: 2026-04-09T14:00:00
expires: 2026-04-10T14:00:00
status: rejected
rejected_by: human
rejected_at: 2026-04-09T16:45:00
rejection_reason: "Email tone inappropriate for client relationship"
---
```

For a system-generated timeout rejection (not this skill — for reference only),
the frontmatter uses `rejected_by: system` instead of `rejected_by: human`.

---

### Step 7 — Append rejection details section to file

After moving the file, append the following section to the end of the file body:

```markdown
---

## REJECTION DETAILS

**Rejected By:** Human
**Rejected At:** <timestamp, e.g. 2026-04-09 16:45:00>
**Reason:** <user's full rejection reason>

**Next Steps:**
- Can be resubmitted with modifications
- Review rejection reason before resubmitting
- Contact team for guidance if needed
```

This section is appended to the file in `Rejected/` — it is not part of the
frontmatter and is intended for human readability when browsing the archive.

---

### Step 8 — Update Dashboard

Call `helpers/dashboard_updater.py` after every rejection:

- Decrement `Pending Approvals` counter
- Increment `Actions Rejected` counter
- Add activity entry: `"Rejected: <action_type> — <first 40 characters of reason>"`

---

### Step 9 — Log rejection

Append two entries to `logs/approvals.log` (create the file if it does not exist):

```
[2026-04-09 16:45:00] REJECTED | LINKEDIN_POST_20260409_110000.md | Rejected by: human
[2026-04-09 16:45:00] REASON   | "Post content needs revision before publishing"
```

The second line always uses the `REASON` label and contains the full rejection
reason in quotes. No action content (email body, post text) is written to this log.

---

### Step 10 — Clean up and report

**Single rejection:**

```
Rejected: LINKEDIN_POST_20260409_110000.md
Reason: Post content needs revision before publishing
File moved to: Rejected/
Action NOT executed.
Dashboard updated.
```

**"Reject all" summary:**

```
Rejection Summary (3 processed):
  [1] EMAIL_DRAFT_20260409_140000.md   → send_email    → rejected
  [2] LINKEDIN_POST_20260409_110000.md → linkedin_post → rejected
  [3] EMAIL_DRAFT_20260408_150000.md   → send_email    → rejected [was EXPIRED]

Reason applied to all: "Need to review strategy first"
3 rejected. No actions were executed.
Dashboard updated.
```

---

## How to Run

This skill performs pure file operations and logging. No external Python execution
helper is called (unlike `approve-action`). The skill uses only file tools and the
dashboard updater.

```
File operations (no module call needed):
  1. Read .md files from AI_Employee_Vault/Pending_Approval/
  2. Parse YAML frontmatter from each file
  3. Move selected file(s) to AI_Employee_Vault/Rejected/
  4. Overwrite frontmatter fields in moved file
  5. Append ## REJECTION DETAILS section to file body

Dashboard updates: helpers.dashboard_updater
  update_activity(vault_path, message)
  update_stats(vault_path, stat_name, value, operation)
    — decrement tasks pending, increment actions rejected

Logging: append to logs/approvals.log (create if absent)
  Two lines per rejection: REJECTED line + REASON line
```

---

## Output — Vault Card Format

No new vault card is created. The existing approval file is updated in place and
moved from `Pending_Approval/` to `Rejected/`.

**Full frontmatter of a rejected file:**

```yaml
---
action_type: send_email
created: 2026-04-09T14:00:00
expires: 2026-04-10T14:00:00
status: rejected
rejected_by: human
rejected_at: 2026-04-09T16:45:00
rejection_reason: "Email tone inappropriate for client relationship"
---
```

**Rejected file body — appended section:**

```markdown
---

## REJECTION DETAILS

**Rejected By:** Human
**Rejected At:** 2026-04-09 16:45:00
**Reason:** Email tone inappropriate for client relationship

**Next Steps:**
- Can be resubmitted with modifications
- Review rejection reason before resubmitting
- Contact team for guidance if needed
```

**Log format — two entries per rejection (logs/approvals.log):**

```
[2026-04-09 16:45:00] REJECTED | EMAIL_DRAFT_20260409_140000.md | Rejected by: human
[2026-04-09 16:45:00] REASON   | "Email tone inappropriate for client relationship"
```

Contrast with a system timeout entry (written by a separate timeout checker, not
this skill):

```
[2026-04-10 14:00:01] REJECTED | EMAIL_DRAFT_20260409_140000.md | Rejected by: system
[2026-04-10 14:00:01] REASON   | "Approval timeout — 24 hours elapsed"
```

---

## Expected Output

**Example 1 — "reject #2" (LinkedIn post):**

```
You selected:
  [2] linkedin_post — "We are thrilled to announce our Q2 results…"
      File: LINKEDIN_POST_20260409_110000.md

Why are you rejecting this action?
```

User replies: "Wrong recipient"

```
Rejected: LINKEDIN_POST_20260409_110000.md
Reason: Wrong recipient
File moved to: Rejected/
Action NOT executed.
Dashboard updated.
```

**Example 2 — "reject the email draft" (by description):**

```
You selected:
  [1] send_email — To: client@example.com | Subject: Q2 Update
      File: EMAIL_DRAFT_20260409_140000.md

Why are you rejecting this action?
```

User replies: "Needs revision, tone too casual"

```
Rejected: EMAIL_DRAFT_20260409_140000.md
Reason: Needs revision, tone too casual
File moved to: Rejected/
Action NOT executed.
Dashboard updated.
```

**Example 3 — "reject all pending approvals":**

```
Why are you rejecting all pending actions? This reason will apply to each.
```

User replies: "Need to review strategy first"

```
Rejection Summary (3 processed):
  [1] EMAIL_DRAFT_20260409_140000.md   → send_email    → rejected
  [2] LINKEDIN_POST_20260409_110000.md → linkedin_post → rejected
  [3] EMAIL_DRAFT_20260408_150000.md   → send_email    → rejected [was EXPIRED]

Reason applied to all: "Need to review strategy first"
3 rejected. No actions were executed.
Dashboard updated.
```

**Example 4 — no pending approvals:**

```
No pending approvals found.
There are no actions waiting for a decision.
```

**Example 5 — empty reason (blocked):**

```
A rejection reason is required for the audit trail. Please provide a reason.
```

**Example 6 — invalid selection:**

```
Invalid action number/file: "7"
Please choose from the list above (1–3) or enter a valid filename.
```

**Example 7 — file not found:**

```
Approval file not found: EMAIL_DRAFT_20260409_140000.md
It may have already been processed. Refreshing the list…
```

---

## Dependencies

Python files that must exist:
- `helpers/dashboard_updater.py` — Dashboard activity and counter updates

No execution helpers are required — this skill never triggers email or LinkedIn
sending. It is a pure archive-and-log operation.

Vault folders (created automatically if absent):
- `AI_Employee_Vault/Pending_Approval/`
- `AI_Employee_Vault/Rejected/`

Log file (created automatically if absent):
- `logs/approvals.log` — shared with `approve-action`; two lines per rejection

---

## Notes

- **NEVER** execute the action when rejecting. This skill's sole job is to decline
  and archive. There is no code path that calls `send_email()` or `post_to_linkedin()`.
- The `rejected_by: human` field in frontmatter distinguishes manual rejections from
  `rejected_by: system` timeout rejections. Never write `rejected_by: system` from
  this skill — that label belongs to the timeout checker only.
- Rejected files are **never deleted**. They remain in `Rejected/` indefinitely as
  an audit trail. The user can review them, learn from the rejection reason, and
  create a new draft if they wish to resubmit.
- Expired files may be rejected by this skill. Expiry is flagged informational only
  (`[EXPIRED]` in the list) and does not block a manual rejection.
- The rejection reason is saved in three places: frontmatter (`rejection_reason`),
  the `## REJECTION DETAILS` section appended to the file body, and the `REASON`
  line in `logs/approvals.log`. All three must be written before reporting success.
- For "reject all", if any individual file operation fails (e.g. file not found
  mid-batch), skip that file, report the error in the summary, and continue with
  the remaining files. Do not abort the entire batch.
- Action content (email body, post text) is never written to `logs/approvals.log`.
  Only the filename, `rejected_by`, and the user's rejection reason appear in the log.
- If the user wants to resubmit a rejected action, they must trigger `send-email`
  or `post-linkedin` again from scratch. The rejected file in `Rejected/` is not
  reused — it serves as a historical reference only.
- `logs/approvals.log` is shared with `approve-action`. Both skills append to the
  same file. Entries are distinguished by the `APPROVED`/`REJECTED`/`EXECUTED`/`REASON`
  label at the start of each line.
