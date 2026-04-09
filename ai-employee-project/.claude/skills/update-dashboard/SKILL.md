---
name: update-dashboard
description: "Updates Dashboard.md with activities and stats"
triggers:
  - update dashboard
  - refresh dashboard
  - log activity
  - update stats
config:
  dashboard_path: ~/Desktop/Hackathon/Hackathon0/AI_Employee_Vault/Dashboard.md
  max_activity_entries: 20
---

# Skill: update-dashboard

Reads `Dashboard.md` from the vault, applies one or more targeted updates
(activity log, stat counter, component status, or full vault resync), then
writes the file back. Implemented in `helpers/dashboard_updater.py`.

---

## Purpose

- Keeps Dashboard.md accurate after every skill run so the AI employee's status is always visible
- Provides a timestamped activity log of everything the system has done
- Tracks key counters: files monitored, emails checked, tasks in each vault folder
- Shows live status of each system component (running, offline, error)
- Acts as the single post-run step called by all other skills

---

## How to Run

**CLI (from project root):**
```
cd ~/Desktop/Hackathon/Hackathon0/ai-employee-project

# Log an activity entry
python -m helpers.dashboard_updater --activity "File monitor scanned ~/Downloads - 2 new files"

# Set a stat to an exact value
python -m helpers.dashboard_updater --stat files_monitored --value 5

# Increment a stat
python -m helpers.dashboard_updater --stat emails_checked --value 1 --operation increment

# Update a component status
python -m helpers.dashboard_updater --component "File Monitor" --status running
python -m helpers.dashboard_updater --component "Gmail Monitor" --status offline
python -m helpers.dashboard_updater --component "Inbox Processor" --status error --notes "Parse failed"

# Resync all vault folder counts
python -m helpers.dashboard_updater --refresh-counts
```

**From Python (import):**
```
Module:    helpers.dashboard_updater
Functions: update_activity(vault_path, message)
           update_stats(vault_path, stat_name, value, operation='set')
           update_component_status(vault_path, component, status, notes='')
           refresh_vault_counts(vault_path)
```

---

## Process

1. Read `Dashboard.md` from `~/Desktop/Hackathon/Hackathon0/AI_Employee_Vault/`
2. Determine which operation(s) to apply based on what just ran (see Operations below)
3. Apply each operation by editing the relevant section or table row in place
4. Update the `_Last updated:_` timestamp at the top of the file
5. Write the file back

---

## Operations

### A — Log an activity entry

Prepend a timestamped line to the `## Recent Activity` section. Keep only the 20 most recent entries.

**Format:** `- \`YYYY-MM-DD HH:MM\` — <message>`

**Example messages:**
- `"File monitor scanned ~/Downloads — 2 new files detected"`
- `"Gmail monitor found 1 priority email — invoice from vendor"`
- `"process-inbox moved 3 cards → Needs_Action"`

---

### B — Update a stat counter

Find the matching row in the `## Quick Stats` table and increment, decrement, or set it to an exact value.

| Stat key | Table label |
|----------|-------------|
| `files_monitored` | Files monitored |
| `emails_checked` | Emails checked |
| `tasks_in_inbox` | Tasks in Inbox |
| `tasks_in_needs_action` | Tasks in Needs_Action |
| `tasks_completed` | Tasks completed |

**When to apply:**
- After `file-monitor` → increment `files_monitored` by the number of new cards
- After `gmail-monitor` → increment `emails_checked` by the number of new cards
- After `process-inbox` → decrement `tasks_in_inbox`, increment destination counter

---

### C — Update a component status row

Find the matching row in the `## System Status` table and replace status, last-run time, and notes.

**Valid components:** `File Monitor`, `Gmail Monitor`, `Dashboard Updater`, `Inbox Processor`

| Status value | Displayed as |
|-------------|-------------|
| `ONLINE` | Running |
| `OFFLINE` | Not Running |
| `ERROR` | Error |
| `READY` | Ready |

---

### D — Resync vault counts (full refresh)

Count all `.md` files in each vault folder and set the three task stats to exact values.

1. Count `.md` files in `Vault/Inbox/`
2. Count `.md` files in `Vault/Needs_Action/`
3. Count `.md` files in `Vault/Done/`
4. Set `tasks_in_inbox`, `tasks_in_needs_action`, `tasks_completed` to those counts

Use Operation D after any bulk move (e.g. after `process-inbox` finishes).

---

## Usage Examples

> "Update the dashboard"
> "Refresh dashboard"
> "Log activity to dashboard"
> "Update stats"

**Activity logged:**
```
[update-dashboard] Activity logged: `2026-04-05 14:30` — Gmail monitor found 1 priority email
```

**Stat updated:**
```
[update-dashboard] Stat updated: Emails checked 4 → 5
```

**Component status updated:**
```
[update-dashboard] Status updated: File Monitor → Running at 2026-04-05 14:30
```

**Vault counts synced:**
```
[update-dashboard] Vault counts synced: inbox=3, needs_action=5, done=12
```

---

## Dependencies

- `helpers/dashboard_updater.py` — provides all four update functions
- `helpers/__init__.py` — makes `helpers` a Python package
- `Vault/Dashboard.md` — must exist; created during initial vault setup
- No third-party packages required — standard library only (`re`, `datetime`, `pathlib`)

---

## Notes

- This skill is always the last step after any other skill runs — never skip it
- Operation D (full resync) is preferred over manual +1/-1 updates after bulk operations since it guarantees accuracy
- The `_Last updated:_` line must appear exactly once at the top of Dashboard.md for the timestamp stamp to work
- If a section header (e.g. `## Recent Activity`) is missing from Dashboard.md, log an error and skip that operation rather than failing entirely
- Never truncate or rewrite the entire Dashboard — only edit the targeted section or row
