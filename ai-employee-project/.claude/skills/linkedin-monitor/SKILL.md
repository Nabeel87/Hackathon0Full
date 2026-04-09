---
name: linkedin-monitor
description: "On-demand LinkedIn notification scan without waiting for the 3-minute poll cycle."
tier: silver
triggers:
  - "check linkedin"
  - "check my linkedin"
  - "any linkedin messages"
  - "linkedin notifications"
  - "scan linkedin"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  session_dir: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/.credentials/linkedin_session"
  session_file: "context.json"
  inbox_folder: "Inbox"
---

# Skill: linkedin-monitor

This skill triggers a single, immediate LinkedIn notification scan using the
existing `LinkedInWatcher` class. It creates vault task cards for any new
messages, connection requests, comments, or mentions found, then updates the
Dashboard — all without starting the continuous 3-minute polling loop.

---

## Purpose

- Give the user instant visibility into LinkedIn activity without waiting for the automatic poll interval
- Surface new messages, connection requests, comments, and mentions as actionable vault cards in `Inbox/`
- Keep the Dashboard current with a fresh activity entry and notification count after every on-demand check
- Provide clear, typed error feedback when the session is missing, expired, or rate-limited

---

## Process

### Step 1 — Verify session

Check that `.credentials/linkedin_session/context.json` exists and is non-empty.

If missing or empty:
> "No LinkedIn session found. Run the LinkedIn watcher first to log in:
> `python watchers/linkedin_watcher.py`
> Complete the browser login, then try again."

Stop here if no session is present.

### Step 2 — Run a single check

Instantiate `LinkedInWatcher` with `vault_path` and `session_dir` from config.
Call `check_for_updates()` exactly once. Do **not** call `run()` — that starts
the continuous polling loop and will block indefinitely.

`check_for_updates()` opens a headless browser, restores the saved session from
`context.json`, scrapes both the messaging inbox and the notifications page, and
returns a list of new notification dicts.

### Step 3 — Create task cards

For each notification dict returned by `check_for_updates()`, call
`create_action_file(notification)` to write a `LINKEDIN_<timestamp>_<type>.md`
card to `Vault/Inbox/`.

While iterating, tally counts by notification type:
- messages
- connection requests
- comments
- mentions

### Step 4 — Update Dashboard

After all cards are written, update `Dashboard.md`:
- Set LinkedIn Monitor component status to `ONLINE`
- Add activity entry: `"LinkedIn check: X notification(s) found"` (or `"No new notifications"`)
- Increment the `linkedin_checked` stat by the total count of notifications found

### Step 5 — Report summary

Reply to the user with a breakdown by type.

If notifications were found:
> "Found X LinkedIn notification(s):
>  - Y new message(s)
>  - Z connection request(s)
>  - W comment(s) / mention(s)
>  Files created in Inbox/"

If nothing new:
> "No new LinkedIn notifications found."

---

## How to Run

Call the watcher in single-check mode — instantiate the class, call
`check_for_updates()` once, then call `create_action_file()` for each result.
Never call `run()` from this skill.

```
Module:  watchers.linkedin_watcher
Class:   LinkedInWatcher(vault_path, session_dir, check_interval=180)

Arguments:
  vault_path   — from config.vault_path
  session_dir  — from config.session_dir

Methods (call in this order):
  check_for_updates()          → list of notification dicts (one per new item)
  create_action_file(item)     → Path  (call once per dict returned above)

Do NOT call:
  run()                        — starts the continuous 180s polling loop
```

Error conditions returned by `check_for_updates()`:
- Empty list + log line "Session expired" → session is stale, require re-login
- Empty list + log line "Rate limit"      → back off, advise user to retry
- Empty list with no errors               → no new notifications (normal)

---

## Output — Vault Card Format

Each card written to `Inbox/` has this frontmatter:

```yaml
---
type: linkedin_notification
notification_type: message        # message | connection_request | comment | mention
from: "Sender Name"
content_preview: "First 100 characters of the notification text..."
received: 2026-04-09T15:30:00
priority: normal                  # normal | high
status: pending
url: "https://www.linkedin.com/..."
---
```

Card filename pattern: `LINKEDIN_<YYYYMMDD_HHMMSS>_<type>.md`

Examples:
- `LINKEDIN_20260409_153000_message.md`
- `LINKEDIN_20260409_153001_connection_request.md`
- `LINKEDIN_20260409_153002_comment.md`

### Priority rules

`priority: high` is set when the notification is a message containing any of
these keywords: `urgent`, `asap`, `important`, `invoice`, `payment`.
All other notifications use `priority: normal`.

---

## Expected Output

**Notifications found (3 items):**

```
Found 3 LinkedIn notification(s):
  - 2 new message(s)
  - 1 connection request(s)
  - 0 comment(s) / mention(s)

Files created in Inbox/:
  LINKEDIN_20260409_153000_message.md
  LINKEDIN_20260409_153001_message.md
  LINKEDIN_20260409_153002_connection_request.md
```

**No new notifications:**

```
No new LinkedIn notifications found.
```

**Session missing:**

```
No LinkedIn session found. Run the LinkedIn watcher first to log in:
  python watchers/linkedin_watcher.py
Complete the browser login, then try again.
```

**Session expired:**

```
LinkedIn session expired. Delete context.json and re-run the watcher to log in again.
```

**Rate limited:**

```
LinkedIn rate limit detected. Try again in a few minutes.
```

---

## Dependencies

Python files that must exist:
- `watchers/linkedin_watcher.py` — `LinkedInWatcher` class with `check_for_updates()` and `create_action_file()`
- `helpers/dashboard_updater.py` — `update_activity()`, `update_component_status()`, `update_stats()`

Credentials required:
- `.credentials/linkedin_session/context.json` — Playwright full browser storage state
  Created automatically on first run of `watchers/linkedin_watcher.py` (interactive login)
  This directory is git-ignored; never commit it

Vault folders that must exist (created automatically if absent):
- `AI_Employee_Vault/Inbox/` — destination for `LINKEDIN_*.md` task cards

---

## Notes

- This skill runs a **single check only** — it does not start the 3-minute polling loop
- The continuous loop is managed by `main.py` (the orchestrator); use this skill for immediate, on-demand checks between cycles
- Deduplication is enforced by `LinkedInWatcher._seen_ids`: notifications already processed in the current session will not produce duplicate cards
- Across sessions, deduplication relies on the `data-urn` or `data-notification-id` attributes scraped from LinkedIn; items with no stable ID use a fallback slug derived from sender name, type, and relative timestamp
- If Playwright is not installed, the watcher will raise `RuntimeError` — direct the user to run `pip install playwright && playwright install chromium`
- This skill is read-only: it never posts, sends messages, accepts connection requests, or modifies any LinkedIn data
- The session file `context.json` is refreshed (re-saved) after every successful check to extend its lifetime
