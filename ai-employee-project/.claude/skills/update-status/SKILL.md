---
name: update-status
description: "Update task status (pending → in_progress → completed) and auto-move completed tasks to Done/."
tier: silver
triggers:
  - "mark task as"
  - "update status"
  - "task completed"
  - "mark complete"
  - "mark as complete"
  - "mark in progress"
  - "mark as in progress"
  - "mark blocked"
  - "mark as blocked"
  - "mark cancelled"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  helper: "helpers/status_updater.py"
---

# Skill: update-status

Updates a task file's frontmatter status and moves completed files to `Done/`
automatically.  Every transition is recorded in a `status_history` list inside
the file for a full audit trail.

---

## Purpose

- Progress tasks through the workflow without manual file editing
- Auto-move completed tasks to `Done/` so `Inbox/` and `Needs_Action/` stay clean
- Preserve the full status history inside the file's YAML frontmatter
- Keep the Dashboard `Recent Activity` and folder counts current after every change

---

## Valid Status Values

| Status | Meaning |
|---|---|
| `pending` | Default — task created, not yet started |
| `in_progress` | User has started working on it |
| `completed` | Work finished — file moved to `Done/` automatically |
| `blocked` | Waiting on something external before work can continue |
| `cancelled` | No longer needed |

---

## Process

### Step 1 — Identify the task

Accept either form from the user:

- **By filename**: `"Update status for LINKEDIN_20260412_153000_message.md"`
- **By description**: `"Mark the urgent invoice email as completed"`

If the user gives a description, search `Inbox/` and `Needs_Action/` for files
whose `from`, `content_preview`, or `notification_type` frontmatter fields match
the description.  If exactly one file matches, proceed.  If multiple match, list
them and ask the user to confirm which one.

### Step 2 — Determine the new status

If the user's phrasing maps unambiguously to a status, use it directly:

| User says | Status |
|---|---|
| "mark as in progress", "start", "working on it" | `in_progress` |
| "mark complete", "done", "finished", "completed" | `completed` |
| "blocked", "waiting", "on hold" | `blocked` |
| "cancel", "ignore", "not needed" | `cancelled` |

If the intent is ambiguous, ask:
> "What status should I set? Options: `in_progress`, `completed`, `blocked`, `cancelled`"

Optionally ask for notes if the user mentions a reason (e.g. "blocked waiting for
client approval" → notes = `"waiting for client approval"`).

### Step 3 — Run the status updater

Call `helpers/status_updater.py` via the module interface:

```
Module:  helpers.status_updater
Function: update_task_status(vault_path, task_file, new_status, notes="")

Arguments:
  vault_path  — from config.vault_path
  task_file   — filename resolved in Step 1
  new_status  — status resolved in Step 2
  notes       — optional reason string from user
```

Or via CLI:

```bash
python helpers/status_updater.py <filename> --status <new_status> [--notes "<reason>"] --vault "<vault_path>"
```

The helper searches these vault folders in order when the filename alone is
given: `Inbox`, `Needs_Action`, `Pending_Approval`, `Approved`, `Rejected`,
`Plans`, `Archive`, `Reports`, `Done`.

### Step 4 — Handle completion routing

When `new_status = "completed"`, `status_updater.py` automatically:

1. Writes the updated frontmatter to `Done/<filename>`
2. Deletes the original file from its current folder
3. Handles name collisions by appending `_1`, `_2`, etc.

No extra steps needed — the move is handled inside the helper.

### Step 5 — Update Dashboard

After a successful status update, refresh the dashboard:

```
Function: helpers.dashboard_updater.update_activity(vault_path, message)
Message:  "Status update: <filename> → <new_status>" [+ "(notes)" if notes given]
```

Then call `refresh_vault_counts(vault_path)` to sync all folder counts.

### Step 6 — Report to user

**Success — non-completed:**
> "Updated `LINKEDIN_20260412_message.md`: `pending` → `in_progress`"

**Success — completed:**
> "Completed `LINKEDIN_20260412_message.md` — moved to `Done/`"

**Blocked with notes:**
> "Updated `EMAIL_20260412_invoice.md`: `in_progress` → `blocked`
> Notes: waiting for client approval"

**File not found:**
> "Could not find a task file matching `<input>`.
> Check `Inbox/` and `Needs_Action/` for the correct filename."

---

## Status History Format

Every call to `update_task_status()` appends an entry to `status_history` in
the file's YAML frontmatter:

```yaml
status: completed
status_updated: "2026-04-12T11:30:00"
status_history:
  - from: pending
    to: in_progress
    timestamp: "2026-04-12T10:00:00"
    notes: "Started working on task"
  - from: in_progress
    to: completed
    timestamp: "2026-04-12T11:30:00"
    notes: "Task completed successfully"
```

The history is never truncated — all transitions are preserved.

---

## Usage Examples

**Mark a LinkedIn message as in progress:**
```
User:  "Mark the LinkedIn message from Nabil as in progress"
Skill: Searches Inbox/ → finds LINKEDIN_20260412_153000_message.md (from: Nabil)
       Calls update_task_status(..., "in_progress")
Reply: "Updated LINKEDIN_20260412_153000_message.md: pending → in_progress"
```

**Mark an invoice email as completed:**
```
User:  "Mark the invoice email as completed"
Skill: Searches Inbox/ + Needs_Action/ → finds EMAIL_20260412_invoice.md
       Calls update_task_status(..., "completed")
       File moved to Done/ automatically
Reply: "Completed EMAIL_20260412_invoice.md — moved to Done/"
```

**Mark a task as blocked with a reason:**
```
User:  "Mark the client project task as blocked, waiting for approval"
Skill: Finds matching file → Calls update_task_status(..., "blocked", "waiting for approval")
Reply: "Updated TASK_20260412_client_project.md: in_progress → blocked
        Notes: waiting for approval"
```

---

## Dependencies

Python files that must exist:
- `helpers/status_updater.py` — `update_task_status()` and convenience wrappers
- `helpers/dashboard_updater.py` — `update_activity()`, `refresh_vault_counts()`

Vault folders used:
- `Inbox/`, `Needs_Action/` — where pending/in-progress tasks live
- `Done/` — destination for completed tasks (auto-created if absent)

---

## Notes

- This skill **never** creates new task files — it only updates existing ones
- If the target file has no `status` field, `status_updater.py` sets `old_status` to `"unknown"` and proceeds normally
- The `blocked` and `cancelled` statuses do **not** trigger a file move — files stay in their current folder
- Completed tasks in `Done/` can still have their status corrected by calling this skill with the filename directly (full-path input bypasses the folder search)
