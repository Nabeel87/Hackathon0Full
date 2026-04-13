---
name: whatsapp-monitor
description: "Check WhatsApp for unread business messages manually"
tier: silver
triggers:
  - check whatsapp
  - check my whatsapp
  - any new whatsapp
  - whatsapp messages
  - scan whatsapp
  - whatsapp urgent
config:
  keywords:
    - urgent
    - asap
    - meeting
    - invoice
    - payment
    - deadline
    - report
    - client
    - project
    - important
    - action
    - help
  high_priority_keywords:
    - urgent
    - asap
    - emergency
    - critical
    - deadline
    - important
    - action required
    - immediately
    - right now
    - waiting
    - help
    - client
    - payment
  session_path: ~/.credentials/whatsapp_session/context.json
  vault_inbox: ~/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault/Inbox
  vault_needs_action: ~/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault/Needs_Action
  max_messages_per_check: 10
---

# Skill: whatsapp-monitor

Triggers a one-shot WhatsApp Web scan for unread messages containing business
keywords, then creates structured task cards in the vault — routed to
`Needs_Action/` for high-priority messages or `Inbox/` for normal-priority.
Read-only monitoring via Playwright browser automation — never sends, deletes,
or modifies any WhatsApp messages.

---

## Purpose

- Surfaces important WhatsApp messages (urgent requests, client issues, invoices, payments) as actionable vault cards without waiting for the 60-second automatic poll
- Bridges WhatsApp Web and the vault pipeline so messages are triaged alongside email and file tasks
- Routes by priority: high-urgency messages go directly to `Needs_Action/`, others land in `Inbox/`
- Deduplicates: already-logged messages (matched by contact + timestamp slug) are skipped on repeat runs
- Filters out personal/casual messages (no business keywords) and UI noise (badges, Typing..., Online)
- Read-only access — monitors only; no message sending, deletion, or modification at any point

---

## Process

1. Add the project root to the Python path so the `watchers` package is importable
2. Instantiate `WhatsAppWatcher` with `vault_path` pointing to the AI Employee Vault
3. Call `_ensure_session()` — checks for a saved Playwright browser context at `~/.credentials/whatsapp_session/context.json`; if missing, prompts the user then calls `_login_and_save_session()` for the QR login flow
4. Call `check_for_updates()` once — opens a headless Chromium browser, loads the saved session, navigates to WhatsApp Web, waits for the chat list to render, then scans all chat list items for unread badge indicators
5. For each chat with an unread badge, call `_extract_message_data(chat_element)` which internally calls:
   - `_extract_sender_name(element)` — gets clean contact name from title attribute
   - `_extract_message_text(element)` — gets text and calls `_clean_message_text()`
   - `_is_notification_badge(text)` — skips pure-digit or empty elements
6. Filter extracted messages to those whose contact name or text contains at least one keyword from `config.keywords`; deduplicate against `_seen_ids` and already-logged vault cards
7. If more than 10 messages match, process the first 10 and log a warning about the remainder
8. For each filtered message, call `create_action_file(item)` — detects priority and routes:
   - **HIGH priority** → writes `WHATSAPP_*.md` to `Vault/Needs_Action/`
   - **NORMAL priority** → writes `WHATSAPP_*.md` to `Vault/Inbox/`
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
Methods:       _ensure_session()                -> verifies saved session exists
               _login_and_save_session()        -> headed browser QR login + save
               check_for_updates()             -> list of message dicts
               create_action_file(item)        -> Path of created vault card
               detect_priority(text)           -> "high" or "normal"
               _extract_sender_name(element)   -> clean contact name
               _extract_message_text(element)  -> cleaned message text
               _clean_message_text(raw)        -> removes UI artifacts
               _is_notification_badge(text)    -> True if badge-only element
               _create_message_fingerprint(sender, msg) -> dedup fingerprint
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
1. A visible Chromium browser window opens automatically (`_login_and_save_session`)
2. WhatsApp Web loads and shows its QR code
3. Open WhatsApp on your phone → Linked Devices → Link a Device → scan the QR code
4. Wait for the chat list to appear (confirms successful login)
5. Session is saved to `~/.credentials/whatsapp_session/context.json`
6. Browser closes automatically

After first-time setup, all subsequent skill invocations run headless with no
QR code needed.

**Session location:**
```
~/.credentials/whatsapp_session/context.json   <- auto-created on first login, never commit this
```

This file is listed in `.gitignore`.

---

## Message Format Handling

WhatsApp messages arrive in various formats — the watcher cleans them automatically:

**Clean messages:**
```
John: Need the report ASAP
```

**With timestamps (stripped):**
```
Input : John 10:36 AM: Meeting at 3 PM
Output: John: Meeting at 3 PM
```

**With UI artifacts (stripped):**
```
Typing..., Online, last seen, Photo, Video, Sticker, GIF, Audio
```

**Notification badges (skipped):**
```
3, 12, 99+   <- pure-digit elements, dropped before processing
```

**Deduplication:**
- Content fingerprint: `sender + first 50 chars of message`
- Timestamp ID: `contact_slug + YYYYMMDD_HHMMSS`
- Both checks run before creating a file

---

## Priority Routing

| Priority | Trigger keywords | Destination |
|----------|-----------------|-------------|
| **high** | urgent, asap, emergency, critical, deadline, important, action required, immediately, right now, waiting, help, client, payment | `Vault/Needs_Action/` |
| **normal** | meeting, invoice, report, project, action (other business words) | `Vault/Inbox/` |

---

## Output: Vault Card Format

Each matching message produces `WHATSAPP_YYYYMMDD_HHMMSS_<contact_slug>.md`
in either `Needs_Action/` or `Inbox/` based on priority:

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
- `high` — message text contains any of the high-priority keywords
- `normal` — contains other business keywords but none of the high-priority list

---

## Expected Output

**Messages found (with priority routing):**
```
[WhatsAppWatcher] Using saved WhatsApp session.
[WhatsAppWatcher] Found 12 chat(s) in list
[WhatsAppWatcher] Checking WhatsApp... found 3 unread message(s) with keywords
[WhatsAppWatcher] Created WHATSAPP_20260409_170022_john_doe.md for message from John Doe (priority: high -> Needs_Action/)
[WhatsAppWatcher] Created WHATSAPP_20260409_163400_acme_corp.md for message from Acme Corp (priority: high -> Needs_Action/)
[WhatsAppWatcher] Created WHATSAPP_20260409_152011_finance_team.md for message from Finance Team (priority: normal -> Inbox/)
[WhatsAppWatcher] DEBUG: Skipped 1 personal message (no business keywords)
```

**No matching messages:**
```
[WhatsAppWatcher] Using saved WhatsApp session.
[WhatsAppWatcher] Found 8 chat(s) in list
[WhatsAppWatcher] Checking WhatsApp... found 0 unread message(s) with keywords
```

**Session not found (first run):**
```
[WhatsAppWatcher] No saved session found.
Run: python watchers/whatsapp_watcher.py
A browser will open - scan the QR code with your phone to create a session.
```

**Session expired:**
```
[WhatsAppWatcher] WhatsApp session appears to have expired.
Error: WhatsApp session expired - manual re-login required.
Delete ~/.credentials/whatsapp_session/context.json and re-run the watcher to scan QR code again.
```

---

## Security Notes

| Property | Detail |
|----------|--------|
| Access mode | Read-only — monitor only, no sending or deleting |
| Data stored | Contact name, first 100 chars of message preview only |
| Credentials | Local disk only, never committed to git |
| Session refresh | If session expires, delete `context.json` and re-run the QR login flow |
| Network calls | Only to `web.whatsapp.com` via local Chromium instance |
| Keyword filter | Personal chats without business keywords are never logged |

---

## Dependencies

- `watchers/whatsapp_watcher.py` — must exist; provides `WhatsAppWatcher`
- `watchers/base_watcher.py` — base class, required by `whatsapp_watcher.py`
- `helpers/whatsapp_helper.py` — utility functions for message cleaning and formatting
- `~/.credentials/whatsapp_session/context.json` — auto-created on first QR login
- `playwright` Python package with Chromium browser (`playwright install chromium`)
- `Vault/Inbox/` folder — created automatically if missing
- `Vault/Needs_Action/` folder — created automatically for high-priority messages
- `update-dashboard` skill — called after cards are written to refresh the activity log

---

## Troubleshooting

**Session expired:**
```
rm ~/.credentials/whatsapp_session/context.json
python watchers/whatsapp_watcher.py
```

**Browser doesn't open:**
```
playwright install chromium
```
Or manually open `https://web.whatsapp.com` and scan QR code.

**No messages detected:**
- Check if messages contain business keywords
- Verify messages are unread (have badge indicator)
- Check watcher logs for filtering details

**Duplicate messages:**
- Deduplication runs on both content fingerprint and timestamp ID
- Check `_seen_ids` in watcher logs
- Clearing seen_messages: restart the watcher process

---

## Notes

- Keywords can be extended by editing `config.keywords` / `config.high_priority_keywords` in this frontmatter and updating the constants in `watchers/whatsapp_watcher.py`
- Message IDs are derived from `<contact_slug>_<timestamp>` — do not rename vault cards manually as this breaks deduplication
- WhatsApp Web CSS selectors may drift when WhatsApp updates its frontend; if the scan returns zero results unexpectedly, check the selector constants in `watchers/whatsapp_watcher.py`
- The automatic background watcher (via `main.py` scheduler) runs every 60 seconds; this skill is for immediate on-demand checks only
- Rate limit: maximum 10 messages processed per check to prevent vault spam; a warning is logged if more than 10 are found
- Phone numbers are not exposed in WhatsApp Web's chat list view; the `phone` field will be empty unless extracted from an open conversation
- This skill is Silver tier — requires Playwright browser automation; Bronze tier watchers use API calls only
- Session expires approximately every 30 days; the watcher will raise a clear error directing the user to re-scan
