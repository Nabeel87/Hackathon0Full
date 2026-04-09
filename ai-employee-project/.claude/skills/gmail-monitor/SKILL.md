---
name: gmail-monitor
description: "Monitors Gmail inbox for important emails"
triggers:
  - check gmail
  - check my email
  - scan inbox
  - monitor email
config:
  scopes:
    - https://www.googleapis.com/auth/gmail.readonly
  keywords:
    - urgent
    - asap
    - invoice
    - payment
  credentials_dir: ~/Desktop/Hackathon/Hackathon0/ai-employee-project/.credentials
  vault_inbox: ~/Desktop/Hackathon/Hackathon0/AI_Employee_Vault/Inbox
---

# Skill: gmail-monitor

Checks Gmail for unread priority emails matching keywords, then creates a
structured task card in the vault Inbox for each match. Read-only OAuth2 —
never sends, deletes, or modifies anything in Gmail.

---

## Purpose

- Surfaces important emails (urgent requests, invoices, payments) as actionable vault cards
- Bridges Gmail and the vault pipeline so emails get triaged alongside file tasks
- Eliminates the need to manually watch Gmail — the AI employee checks on demand
- Deduplicates: already-logged message IDs are skipped on repeat runs
- Uses `gmail.readonly` scope only — zero write access to the inbox

---

## Process

1. Add the project root to the Python path so the `watchers` package is importable
2. Instantiate `GmailWatcher` with `vault_path` pointing to the AI Employee Vault
3. Call `_get_service()` to authenticate — reuses `token.json` if it exists, auto-refreshes if expired, opens browser only on very first run
4. Call `check_for_updates()` once — queries Gmail with `is:unread label:inbox ("urgent" OR "asap" OR "invoice" OR "payment")`
5. For each returned email not already logged, call `create_action_file(item)` — writes an `EMAIL_*.md` card to `Vault/Inbox/`
6. After all cards are written, invoke the `update-dashboard` skill

---

## How to Run

**Standalone (single-shot check):**
```
cd ~/Desktop/Hackathon/Hackathon0/ai-employee-project
python watchers/gmail_watcher.py
```

Optional arguments:
```
python watchers/gmail_watcher.py <vault_path> <check_interval_seconds>
```

**From Python (import):**
```
Project root:  ~/Desktop/Hackathon/Hackathon0/ai-employee-project
Module:        watchers.gmail_watcher
Class:         GmailWatcher(vault_path)
Methods:       _get_service()           -> authenticates, returns Gmail API service
               check_for_updates()      -> list of email dicts
               create_action_file(item) -> Path of created vault card
```

The script adds `PROJECT_ROOT` to `sys.path` automatically when run standalone.
Call `check_for_updates()` exactly once per invocation — no loop, no sleep.

---

## Gmail API Setup (first time only)

1. Go to Google Cloud Console → create project `ai-employee`
2. Enable the **Gmail API** under APIs & Services → Library
3. Create **OAuth client ID** → Desktop app → download JSON
4. Save the downloaded file to `.credentials/credentials.json`

**Credentials location:**
```
.credentials/credentials.json   ← downloaded from Google Cloud Console
.credentials/token.json         ← auto-created on first run, never commit this
```

Both files are listed in `.gitignore`.

---

## Security Notes

| Property | Detail |
|----------|--------|
| Scope | `gmail.readonly` — zero write access |
| Data stored | Sender, subject, 200-char snippet only — no full email body |
| Credentials | Local disk only, never committed to git |
| Token refresh | Automatic — no manual intervention needed |
| Network calls | Only to `gmail.googleapis.com` |

---

## Output: Vault Card Format

Each matching email produces `Vault/Inbox/EMAIL_YYYYMMDD_HHMMSS_<msgid>_<subject>.md`:

```yaml
---
type: email
from: "billing@vendor.com"
subject: "Invoice for April services"
received: "2026-04-05 14:30:55 UTC"
priority: normal
status: pending
message_id: "1a2b3c4d5e6f7a8b"
---
```

**Priority rules:**
- `high` — subject or snippet contains `urgent` or `asap`
- `normal` — contains `invoice` or `payment` (finance action checklist attached)

---

## Usage Examples

> "Check Gmail"
> "Check my email"
> "Any important emails?"
> "Scan my inbox"

**Emails found:**
```
[gmail-monitor] Authenticating with Gmail API...
[gmail-monitor] Query: is:unread label:inbox ("urgent" OR "asap" OR "invoice" OR "payment")
[gmail-monitor] 2 matching unread email(s) found.
  [new]  Card created: EMAIL_20260405_143055_1a2b3c4d_Invoice_for_April.md
  [new]  Card created: EMAIL_20260405_091200_5e6f7a8b_Urgent_contract_review.md
[gmail-monitor] 2 new inbox card(s) created.
[gmail-monitor] Calling update-dashboard to refresh status...
```

**Nothing new:**
```
[gmail-monitor] Authenticating with Gmail API...
[gmail-monitor] Query: is:unread label:inbox ("urgent" OR "asap" OR "invoice" OR "payment")
[gmail-monitor] 0 matching unread email(s) found.
[gmail-monitor] No new priority emails to log.
```

---

## Dependencies

- `watchers/gmail_watcher.py` — must exist; provides `GmailWatcher`
- `watchers/base_watcher.py` — base class, required by `gmail_watcher.py`
- `.credentials/credentials.json` — downloaded from Google Cloud Console (one-time setup)
- `.credentials/token.json` — auto-created on first run
- `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` Python packages
- `Vault/Inbox/` folder — created automatically if missing

---

## Notes

- Keywords can be extended by editing `config.keywords` in this frontmatter and updating `KEYWORDS` in `watchers/gmail_watcher.py`
- Message IDs are stored in vault card filenames for deduplication — do not rename cards manually
- If `token.json` is deleted or revoked, the next run will re-open the browser for authorization
- This skill checks `label:inbox OR label:important` — Spam and Promotions labels are not scanned
- Always call `update-dashboard` after this skill to keep email count and activity log current
