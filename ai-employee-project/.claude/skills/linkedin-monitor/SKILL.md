---
name: linkedin-monitor
description: Manually trigger a single LinkedIn notification check without waiting for the watcher's 3-minute polling interval.
tier: silver
triggers:
  - "check linkedin"
  - "check my linkedin"
  - "any linkedin messages"
  - "linkedin notifications"
  - "linkedin messages"
  - "new linkedin notifications"
dependencies:
  - watchers/linkedin_watcher.py
  - .credentials/linkedin_session/
  - helpers/dashboard_updater.py
---

## Purpose

Run a single on-demand LinkedIn notification check, create task cards in
`Vault/Inbox/` for any new notifications found, and report a summary — without
waiting for the automatic 3-minute polling cycle.

---

## Triggers

This skill activates when the user says any of:

- "check linkedin"
- "check my linkedin"
- "any linkedin messages"
- "linkedin notifications"
- "linkedin messages"
- "new linkedin notifications"

---

## Process

### Step 1 — Check Session

Before running, verify that a saved LinkedIn session exists at
`.credentials/linkedin_session/cookies.json`.

If the session file is missing or empty:
> "⚠️ No LinkedIn session found. Please run the LinkedIn watcher first to log in:
> `python watchers/linkedin_watcher.py`
> Complete the browser login, then try again."

Stop here if no session exists.

### Step 2 — Run Single Check

Execute a one-shot LinkedIn check by instantiating `LinkedInWatcher` and
calling `check_for_updates()` once (do not start the polling loop):

```
python watchers/linkedin_watcher.py --once
```

Or from Python:
```python
from watchers.linkedin_watcher import LinkedInWatcher
watcher = LinkedInWatcher(vault_path=vault_path)
items = watcher.check_for_updates()
```

This opens a headless browser, restores the saved session, scrapes the
LinkedIn notifications page, and returns new notification items.

### Step 3 — Create Task Cards

For each notification returned, `check_for_updates()` automatically creates
a `LINKEDIN_<timestamp>_<type>.md` card in `Vault/Inbox/`.

Notification types and their card filenames:

| Type | Card filename |
|---|---|
| Message | `LINKEDIN_<ts>_message.md` |
| Connection request | `LINKEDIN_<ts>_connection_request.md` |
| Comment | `LINKEDIN_<ts>_comment.md` |
| Mention | `LINKEDIN_<ts>_mention.md` |

Each card includes: sender, content preview, notification URL, priority, and
status `pending`.

### Step 4 — Update Dashboard

After the check completes:

- Update `Dashboard.md` component status: `LinkedIn Monitor Skill → ONLINE`
- Increment **LinkedIn checked** counter by the number of notifications found
- Add activity log entry:
  `LinkedIn Monitor: <N> new notification(s) detected`
  or
  `LinkedIn Monitor: No new notifications`

### Step 5 — Report Summary

Report to the user with one of these responses:

**Notifications found:**
> "✅ LinkedIn check complete.
> Found **3** new notification(s):
> - 1 message from Jane Smith
> - 1 connection request from John Doe
> - 1 comment on your post
>
> Task cards created in `Vault/Inbox/`. Say 'process inbox' to triage them."

**Nothing new:**
> "✅ LinkedIn check complete. No new notifications."

**Session expired:**
> "⚠️ LinkedIn session expired. Please re-run the watcher to log in again:
> `python watchers/linkedin_watcher.py`"

**Rate limited:**
> "⏳ LinkedIn rate limit detected. Try again in 5 minutes."

**Other error:**
> "❌ LinkedIn check failed: <error message>
> Check `logs/main.log` for details."

---

## Dashboard Updates

| Event | Dashboard action |
|---|---|
| Check started | Component status → `ONLINE` |
| Notifications found | Increment LinkedIn checked counter; add activity entry |
| No notifications | Add activity entry: "No new notifications" |
| Session expired | Component status → `OFFLINE` |
| Error | Component status → `OFFLINE`; add activity entry with error |

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `watchers/linkedin_watcher.py` | Performs the actual scrape |
| `.credentials/linkedin_session/cookies.json` | Saved browser session |
| `helpers/dashboard_updater.py` | Updates Dashboard.md |
| `AI_Employee_Vault/Inbox/` | Destination for task cards |

---

## Usage Examples

> "check linkedin"
> "any linkedin messages?"
> "check my linkedin notifications"
> "linkedin messages"

---

## Notes

- This skill runs a **single check** only — it does not start the continuous watcher loop
- The continuous 3-minute polling loop is managed by `main.py` (orchestrator)
- Use this skill for immediate on-demand checks between polling cycles
- Deduplication is enforced: notifications already logged in any vault folder will not produce duplicate cards
