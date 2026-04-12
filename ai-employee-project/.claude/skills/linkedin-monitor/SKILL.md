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

## LinkedIn Message Format Details

### Message Patterns Detected

LinkedIn messages come in multiple formats that need special handling:

**Pattern 1: Clean Message**
```
Sender Name: message text
```
Example: `"Nabil: check msg asap"`

**Pattern 2: Message with UI Artifacts**
```
Sender Name [timestamp] Sender: message . Active conversation . Press return...
```
Example: `"Nabil Sabir 10:36 AM Nabil: check msg asap . Active conversation"`

**Pattern 3: Notification Badges (Filtered Out)**
```
Just numbers indicating unread count
```
Examples: `"1 new notification"`, `"1 1 new"` — these are **not** actual messages and are filtered out.

---

### Deduplication Logic

The watcher implements two layers of deduplication to avoid creating multiple task cards for the same message:

**Layer 1 — Seen-ID persistence** (`linkedin_seen_ids.json`)
Every processed item's `id` is written to disk. On the next poll, any item whose `id` is already in that file is skipped before any other processing.

**Layer 2 — Content-similarity check (per-poll session)**
Within a single poll cycle, a `session_previews` list tracks the cleaned preview of every item accepted so far. Before accepting a new item, `is_duplicate_message()` strips UI artifacts from both strings and checks substring containment:

| Raw text scraped | Cleaned core | Result |
|---|---|---|
| `"Nabil: check msg asap"` | `"Nabil: check msg asap"` | ✅ Accepted |
| `"Nabil: check msg asap . Active conversation . Press return to go to"` | `"Nabil: check msg asap"` | ⏭️ Skipped (duplicate) |
| `"1 new notification"` | filtered as `"other"` type | ⏭️ Skipped (badge) |

**UI Artifacts Stripped**

The following strings and everything after them are removed from scraped text before any comparison or storage:

```
. Active conversation
. Press return to go to
. Press Enter to
Open the options list
Open the options
conversation with
undefined
```

---

### Data Extraction

**Sender Name Extraction**
1. Tries dedicated DOM selectors: `.msg-conversation-listitem__participant-names`, `.nt-card__text--truncate`, `.notification-item__actor-name`, `span.actor-name`
2. Falls back to the first non-empty line of cleaned `inner_text()`

**Message Text Cleaning**
1. Read raw `inner_text()` from the thread element
2. Pass through `_clean_message_text()` — truncates at first UI artifact
3. Use cleaned text for classification, sender extraction, and preview

**Content Preview**
1. Try targeted snippet selectors first (actual message body elements):
   - `span.msg-s-event-listitem__body`
   - `span.msg-conversation-card__message-snippet-body`
   - `span[class*='message-snippet']`
2. Fall back to first 100 chars of the cleaned full text

**Message ID (for deduplication)**
Priority order:
1. `data-msg-id` attribute
2. `data-event-id` attribute
3. `data-message-id` attribute
4. `data-urn` / `data-entity-urn` / `data-notification-id` / `data-conversation-id`
5. Fallback hash: `_make_uid(sender, type, preview)` — uses **cleaned preview**, not raw timestamp

---

### Filtering Rules

**Messages are SKIPPED if:**
- No text or text shorter than 5 characters after cleaning
- `notification_type` resolves to `"other"` and no `default_type` override applies
- `id` already present in `_seen_ids` (persistent dedup)
- Content-similar to a message already collected this poll cycle (session dedup)
- Element has `aria-label` attribute but no visible text (pure UI control)

**Messages are PROCESSED if:**
- Cleaned text ≥ 5 characters
- Valid notification type resolved
- ID not previously seen
- Not a content-duplicate within the current poll session

---

### Priority Detection

`priority: high` is set when the message text (after cleaning) contains any of:

```
urgent  asap  important  invoice  payment
```

All other items use `priority: normal`.

---

### Known Limitations

1. **LinkedIn UI Changes** — LinkedIn frequently updates their SPA structure. Selectors and UI artifact strings may need updating if messages stop appearing.
2. **Session Expiry** — Browser session expires after ~30 days of inactivity. Delete `context.json` and re-run `watchers/linkedin_watcher.py` to re-authenticate.
3. **Rate Limiting** — Excessive checks (multiple per minute) may trigger LinkedIn's checkpoint/captcha flow. The watcher backs off for 300 seconds when detected.
4. **Headless Mode** — Some LinkedIn features (video calls, certain modal flows) do not render in headless Chromium. The messaging list used here works reliably headless.

---

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Duplicate task cards created | New UI artifact string not in `_UI_ARTIFACTS` | Add the artifact to `_UI_ARTIFACTS` in `linkedin_watcher.py` |
| Wrong sender name extracted | LinkedIn changed name-element class | Update selectors in `_extract_notification_data()` |
| UI artifact text appears in card preview | Artifact string not yet in `_UI_ARTIFACTS` | Add it to the list |
| 0 messages found despite unread threads visible | Unread-indicator selector mismatch (removed) | Verify `_check_messages` scrapes all threads, not just unread |
| `"undefined"` in preview | LinkedIn SPA rendered placeholder | Already stripped by `_clean_message_text()` — if still appears, check artifact list |

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

## Technical Details

### Message Processing Pipeline

```
LinkedIn /messaging/ page
        │
        ▼
Extract thread <li> elements
        │
        ├─ Skip: aria-label-only UI controls
        │
        ▼
For each thread element:
  1. inner_text() → _clean_message_text()     (strip UI artifacts)
  2. _classify_notification()                 (type or "other")
  3. Extract sender name (DOM selector → fallback to first line)
  4. Extract preview (snippet selector → fallback to text[:100])
  5. Resolve stable ID (msg-id attr → data-urn → hash of sender+preview)
  6. Check _seen_ids                          (persistent dedup — skip if seen)
  7. is_duplicate_message()                   (session dedup — skip if similar)
  8. _infer_priority()                        (high / normal)
        │
        ▼
Return new unique items
        │
        ▼
create_action_file() per item → Inbox/LINKEDIN_<ts>_<type>.md
        │
        ▼
_save_seen_ids() → linkedin_seen_ids.json
_save_session()  → context.json (refresh browser state)
```

### Deduplication Strategy

| Layer | Scope | Storage | Key |
|---|---|---|---|
| Seen-ID | Across sessions | `linkedin_seen_ids.json` on disk | `data-urn` / `data-msg-id` / hash |
| Content-similarity | Within one poll cycle | In-memory `session_previews` list | Cleaned preview substring match |

### Key Functions

| Function | Location | Purpose |
|---|---|---|
| `_clean_message_text(text)` | module-level helper | Strip UI artifacts from raw inner_text |
| `is_duplicate_message(new, existing)` | `LinkedInWatcher` method | Session-level content similarity check |
| `_extract_notification_data(el, page, type)` | `LinkedInWatcher` method | Parse one element into a notification dict |
| `_check_messages(page)` | `LinkedInWatcher` method | Scrape /messaging/, apply both dedup layers |
| `_make_uid(sender, type, preview)` | module-level helper | Stable fallback ID from cleaned content |

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
