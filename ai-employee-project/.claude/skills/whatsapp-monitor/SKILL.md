---
name: whatsapp-monitor
description: "On-demand WhatsApp Web scan for unread business messages"
triggers:
  - check whatsapp
  - check my whatsapp
  - any whatsapp messages
  - scan whatsapp
  - whatsapp urgent
config:
  keywords:
    - urgent
    - asap
    - client
    - payment
    - invoice
    - meeting
    - deadline
    - important
  high_priority_keywords:
    - urgent
    - asap
    - emergency
    - critical
    - deadline
    - important
    - client
    - payment
  session_path: ~/.credentials/whatsapp_session/context.json
  vault_inbox: ~/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault/Inbox
  max_messages_per_check: 10
---

# Skill: whatsapp-monitor

Triggers a one-shot WhatsApp Web scan for unread messages containing business
keywords, then creates a structured task card in the vault Inbox for each match.
Read-only monitoring via Playwright browser automation — never sends, deletes,
or modifies any WhatsApp messages.

---

## Purpose

- Surfaces important WhatsApp messages (urgent requests, client issues, invoices, payments) as actionable vault cards without waiting for the 60-second automatic poll
- Bridges WhatsApp Web and the vault pipeline so messages are triaged alongside email and file tasks
- Provides instant on-demand visibility when the user is expecting a critical message
- Deduplicates: already-logged messages (matched by contact + timestamp slug) are skipped on repeat runs
- Read-only access — monitors only; no message sending, deletion, or modification at any point

---

## Process

1. Add the project root to the Python path so the `watchers` package is importable
2. Instantiate `WhatsAppWatcher` with `vault_path` pointing to the AI Employee Vault
3. Call `_ensure_session()` — checks for a saved Playwright browser context at `~/.credentials/whatsapp_session/context.json`; if missing, raises an error directing the user to run the first-time QR login flow
4. Call `check_for_updates()` once — opens a headless Chromium browser, loads the saved session, navigates to WhatsApp Web, waits for the chat list to render, then scans all chat list items for unread badge indicators
5. For each chat with an unread badge, call `_extract_message_data(chat_element)` to parse contact name, message preview text, and timestamp
6. Filter extracted messages to those whose contact name or text contains at least one keyword from `config.keywords`; deduplicate against `_seen_ids` and already-logged vault cards
7. If more than 10 messages match, process the first 10 and log a warning about the remainder
8. For each filtered message, call `create_action_file(item)` — writes a `WHATSAPP_*.md` card to `Vault/Inbox/`
9. After all cards are written, invoke the `update-dashboard` skill to refresh the activity log and stats

---

## How to Run

**Standalone (single-shot check):**
```
cd ~/Desktop/Hackathon/Hackathon0Full/ai-employee-project
python watchers/whatsapp_watcher.py
```

Optional argument:
```
python watchers/whatsapp_watcher.py <vault_path>
```

**From Python (import):**
```
Project root:  ~/Desktop/Hackathon/Hackathon0Full/ai-employee-project
Module:        watchers.whatsapp_watcher
Class:         WhatsAppWatcher(vault_path, check_interval=60)
Methods:       _ensure_session()            -> verifies saved session exists
               check_for_updates()          -> list of message dicts
               create_action_file(item)     -> Path of created vault card
               detect_priority(text)        -> "high" or "normal"
```

Call `check_for_updates()` exactly once per invocation — no loop, no sleep.
The watcher's `run()` loop (inherited from BaseWatcher) is only for the
background scheduler; this skill uses a single-shot call pattern.

---

## First-Time Setup (QR Login)

WhatsApp requires a one-time QR code scan to create a persistent browser session.
This must be done before the skill can run in headless mode.

Run the watcher standalone to trigger the login flow:
```
python watchers/whatsapp_watcher.py
```

The flow:
1. A visible Chromium browser window opens automatically
2. WhatsApp Web loads and shows its QR code
3. Open WhatsApp on your phone → Linked Devices → Link a Device → scan the QR code
4. Wait for the chat list to appear (confirms successful login)
5. Session is saved to `~/.credentials/whatsapp_session/context.json`
6. Browser closes automatically

After first-time setup, all subsequent skill invocations run headless with no
QR code needed.

**Session location:**
```
~/.credentials/whatsapp_session/context.json   ← auto-created on first login, never commit this
```

This file is listed in `.gitignore`.

---

## Security Notes

| Property | Detail |
|----------|--------|
| Access mode | Read-only — monitor only, no sending or deleting |
| Data stored | Contact name, first 100 chars of message preview only — no full message body in logs |
| Credentials | Local disk only, never committed to git |
| Session refresh | If session expires, delete `context.json` and re-run the QR login flow |
| Network calls | Only to `web.whatsapp.com` via local Chromium instance |
| Keyword filter | Personal chats without business keywords are never logged |

---

## Output: Vault Card Format

Each matching message produces `Vault/Inbox/WHATSAPP_YYYYMMDD_HHMMSS_<contact_slug>.md`:

```yaml
---
type: whatsapp_message
from: "John Doe"
message_preview: "Hey, urgent client issue with invoice #1234. Need to discuss ASAP"
received: 2026-04-09T17:00:22
priority: high
status: pending
phone: "+1234567890"
message_id: "john_doe_20260409_170022"
---
```

**Priority rules:**
- `high` — message text contains any of: `urgent`, `asap`, `emergency`, `critical`, `deadline`, `important`, `client`, `payment`
- `normal` — contains other business keywords (`invoice`, `meeting`) but none of the high-priority list

---

## Expected Output

**Messages found:**
```
[WhatsAppWatcher] Using saved WhatsApp session.
[WhatsAppWatcher] Found 12 chat(s) in list
[WhatsAppWatcher] Checking WhatsApp... found 3 unread message(s) with keywords
[WhatsAppWatcher] Created WHATSAPP_20260409_170022_john_doe.md for message from John Doe
[WhatsAppWatcher] Created WHATSAPP_20260409_163400_acme_corp.md for message from Acme Corp
[WhatsAppWatcher] Created WHATSAPP_20260409_152011_finance_team.md for message from Finance Team
[WhatsAppWatcher] 3 new inbox card(s) created.
[WhatsAppWatcher] Calling update-dashboard to refresh status...

Found 3 important WhatsApp messages:
  - John Doe (HIGH): "Hey, urgent client issue with invoice #1234..."
  - Acme Corp (HIGH): "Payment overdue — please confirm receipt ASAP..."
  - Finance Team (normal): "Reminder: invoice deadline is Friday..."
```

**No matching messages:**
```
[WhatsAppWatcher] Using saved WhatsApp session.
[WhatsAppWatcher] Found 8 chat(s) in list
[WhatsAppWatcher] Checking WhatsApp... found 0 unread message(s) with keywords
[WhatsAppWatcher] No important WhatsApp messages to log.

No important WhatsApp messages found.
```

**Session not found (first run):**
```
[WhatsAppWatcher] No saved session found.
Error: WhatsApp session not found.
Run: python watchers/whatsapp_watcher.py
A browser will open — scan the QR code with your phone to create a session.
```

**Session expired:**
```
[WhatsAppWatcher] WhatsApp session appears to have expired.
Error: WhatsApp session expired — manual re-login required.
Delete ~/.credentials/whatsapp_session/context.json and re-run the watcher to scan QR code again.
```

---

## Dependencies

- `watchers/whatsapp_watcher.py` — must exist; provides `WhatsAppWatcher`
- `watchers/base_watcher.py` — base class, required by `whatsapp_watcher.py`
- `~/.credentials/whatsapp_session/context.json` — auto-created on first QR login
- `playwright` Python package with Chromium browser (`playwright install chromium`)
- `Vault/Inbox/` folder — created automatically if missing
- `update-dashboard` skill — called after cards are written to refresh the activity log

---

## Notes

- Keywords can be extended by editing `config.keywords` in this frontmatter and updating `KEYWORDS` in `watchers/whatsapp_watcher.py`
- Message IDs are derived from `<contact_slug>_<timestamp>` — do not rename vault cards manually as this breaks deduplication
- WhatsApp Web CSS selectors may drift when WhatsApp updates its frontend; if the scan returns zero results unexpectedly, check the selector constants in `watchers/whatsapp_watcher.py`
- The automatic background watcher (via `main.py` scheduler) runs every 60 seconds; this skill is for immediate on-demand checks only
- Rate limit: maximum 10 messages processed per check to prevent vault spam; a warning is logged if more than 10 are found
- Phone numbers are not exposed in WhatsApp Web's chat list view; the `phone` field will be empty unless extracted from an open conversation
- This skill is Silver tier — requires Playwright browser automation; Bronze tier watchers use API calls only
