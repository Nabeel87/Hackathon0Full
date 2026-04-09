# AI Employee — Code Documentation

Complete technical reference for every module, class, function, and tool used
in the AI Employee Bronze Tier system.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Entry Point — main.py](#2-entry-point--mainpy)
3. [Watchers](#3-watchers)
   - [base_watcher.py](#31-base_watcherpy)
   - [file_watcher.py](#32-file_watcherpy)
   - [gmail_watcher.py](#33-gmail_watcherpy)
4. [Helpers](#4-helpers)
   - [dashboard_updater.py](#41-dashboard_updaterpy)
   - [inbox_processor.py](#42-inbox_processorpy)
5. [Claude Agent Skills](#5-claude-agent-skills)
   - [file-monitor](#51-file-monitor)
   - [gmail-monitor](#52-gmail-monitor)
   - [process-inbox](#53-process-inbox)
   - [update-dashboard](#54-update-dashboard)
6. [External Tools & Libraries](#6-external-tools--libraries)
7. [Vault Structure](#7-vault-structure)
8. [Configuration Reference](#8-configuration-reference)
9. [Data Flow](#9-data-flow)
10. [Error Handling Patterns](#10-error-handling-patterns)

---

## 1. System Architecture

```
ai-employee-project/
│
├── main.py                        ← Orchestrator: starts & supervises all watchers
│
├── watchers/
│   ├── base_watcher.py            ← Abstract base class for all watchers
│   ├── file_watcher.py            ← Scans filesystem for new files
│   └── gmail_watcher.py           ← Polls Gmail API for priority emails
│
├── helpers/
│   ├── dashboard_updater.py       ← Reads/writes Dashboard.md
│   └── inbox_processor.py         ← Routes Inbox cards to Needs_Action or Done
│
├── .claude/skills/
│   ├── file-monitor/SKILL.md      ← Claude skill: trigger file scanning
│   ├── gmail-monitor/SKILL.md     ← Claude skill: trigger Gmail check
│   ├── process-inbox/SKILL.md     ← Claude skill: trigger inbox triage
│   └── update-dashboard/SKILL.md  ← Claude skill: trigger dashboard refresh
│
├── .credentials/
│   ├── credentials.json           ← OAuth app identity (git-ignored)
│   └── token.json                 ← Personal access token (git-ignored)
│
├── documents/
│   ├── GMAIL_SETUP.md             ← Step-by-step Gmail API setup guide
│   ├── BRONZE_COMPLETE.md         ← Project milestone notes
│   ├── CODE_DOCUMENTATION.md      ← This file
│   └── DEPLOYMENT_GUIDE.md        ← Deployment guide for new machines
│
├── pyproject.toml                 ← Project metadata and dependencies
├── requirements.txt               ← Pinned dependency versions
└── README.md                      ← Project overview
```

**Execution modes:**

| Mode | How it runs | Use case |
|------|-------------|----------|
| Orchestrator (`main.py`) | Threaded polling loop, never exits | Unattended 24/7 operation |
| Standalone watcher | Single-shot scan, exits | Manual invocation, testing |
| Claude skill | Claude reads SKILL.md and executes | Interactive use via Claude Code |
| Helper CLI | Direct CLI, exits | Debugging, scripting |

---

## 2. Entry Point — main.py

**Path:** `main.py`
**Purpose:** Master orchestrator. Starts FileWatcher and GmailWatcher in
separate daemon threads, health-checks them every 5 minutes, auto-restarts
crashed watchers, and shuts down cleanly on CTRL+C or SIGTERM.

### Constants

| Name | Value | Description |
|------|-------|-------------|
| `HEALTH_CHECK_INTERVAL` | `300` | Seconds between health-check log lines |
| `RESTART_DELAY` | `10` | Seconds before restarting a crashed watcher |
| `LOG_DIR` | `<project_root>/logs` | Directory for log file output |
| `LOG_FILE` | `logs/main.log` | Full path to the rolling log file |

### Function: `_setup_logging(log_level)`

```python
def _setup_logging(log_level: str) -> logging.Logger
```

Sets up the root logger with both a file handler (`logs/main.log`) and a
console handler. Creates the `logs/` directory if it does not exist. Clears
existing handlers on re-import to prevent duplicates.

**Parameters:**
- `log_level` — One of `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`

**Returns:** A `logging.Logger` named `"orchestrator"`.

---

### Class: `WatcherThread`

Wraps a `BaseWatcher` subclass in a daemon thread with automatic restart on
crash.

#### `__init__(name, watcher_cls, watcher_kwargs)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Human-readable name, e.g. `"FileWatcher"` |
| `watcher_cls` | `type` | The watcher class to instantiate |
| `watcher_kwargs` | `dict` | Keyword arguments passed to the watcher constructor |

**Instance attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `restart_count` | `int` | Number of times this watcher has been restarted |
| `last_started` | `datetime \| None` | When the thread last started |
| `last_error` | `str \| None` | Last exception message, if any |

#### `start()`
Clears the stop event and spawns a new daemon thread.

#### `stop()`
Sets the stop event, calls `watcher.stop()`, and joins the thread with a
5-second timeout.

#### `is_alive` (property)
`True` if the underlying thread is alive.

#### `_run_loop()` (internal)
The thread target. Instantiates the watcher, then polls `check_for_updates()`
and `create_action_file()` in a loop. Sleeps in 1-second ticks so `stop()`
takes effect promptly. Calls `_update_dashboard()` after any cycle that creates
cards.

#### `_update_dashboard(vault_path, n)` (internal)
Calls `update_activity`, `update_component_status`, `update_stats`, and
`refresh_vault_counts` from `helpers/dashboard_updater.py`. Never raises — logs
a warning if any update fails.

---

### Class: `Orchestrator`

Starts, monitors, and shuts down all watcher threads.

#### `__init__(vault_path, file_interval, gmail_interval)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `vault_path` | `Path` | — | Path to `AI_Employee_Vault/` |
| `file_interval` | `int` | `60` | FileWatcher poll interval in seconds |
| `gmail_interval` | `int` | `120` | GmailWatcher poll interval in seconds |

#### `start()`
Starts all watcher threads and enters `_main_loop()`. Blocks indefinitely.

#### `shutdown()`
Sets the shutdown event, stops all watcher threads, logs a final activity entry
to the dashboard.

#### `_main_loop()` (internal)
Runs until `_shutdown` is set. Calls `_refresh_dashboard()` every 60 seconds
and `_health_check()` every `HEALTH_CHECK_INTERVAL` seconds.

#### `_health_check()` (internal)
Logs alive/dead status for each watcher. Auto-restarts any dead watcher thread.

---

### CLI Arguments

```
python main.py [OPTIONS]

--vault-path PATH       Path to vault root  (default: ~/Desktop/.../AI_Employee_Vault)
--file-interval INT     FileWatcher poll interval in seconds  (default: 60)
--gmail-interval INT    GmailWatcher poll interval in seconds  (default: 120)
--log-level LEVEL       DEBUG | INFO | WARNING | ERROR  (default: INFO)
```

---

## 3. Watchers

### 3.1 base_watcher.py

**Path:** `watchers/base_watcher.py`
**Purpose:** Abstract base class that all watchers inherit from. Defines the
polling loop and the two abstract methods each watcher must implement.

#### Class: `BaseWatcher`

```python
class BaseWatcher(ABC):
    def __init__(self, vault_path: str | Path, check_interval: int = 60)
```

**Constructor parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `vault_path` | `str \| Path` | — | Path to `AI_Employee_Vault/` |
| `check_interval` | `int` | `60` | Seconds between polls |

**Instance attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `self.vault_path` | `Path` | Resolved vault path |
| `self.check_interval` | `int` | Poll interval |
| `self.logger` | `Logger` | Named logger (`FileWatcher` or `GmailWatcher`) |
| `self._running` | `bool` | Loop control flag |

#### Abstract methods (must be implemented by subclasses)

```python
@abstractmethod
def check_for_updates(self) -> list[dict]:
    """Check the source for new items. Returns a list of item dicts."""

@abstractmethod
def create_action_file(self, item: dict) -> Path:
    """Write a vault action/task file for the given item. Returns the file path."""
```

#### `run()`
Main polling loop. Calls `check_for_updates()`, then `create_action_file()` for
each item, then `post_cycle()` if any cards were created. Sleeps via
`_interruptible_sleep()`. Catches `KeyboardInterrupt` to exit cleanly.

#### `post_cycle(created_count)`
Hook called after each cycle where cards were created. Base implementation does
nothing — subclasses override to update the dashboard.

#### `stop()`
Sets `self._running = False`, causing the poll loop to exit within 1 second.

#### `_interruptible_sleep(seconds)` (internal)
Sleeps in 1-second ticks while `self._running` is `True`.

---

### 3.2 file_watcher.py

**Path:** `watchers/file_watcher.py`
**Purpose:** Scans a directory (default `~/Downloads/file_check`) for new
files. Creates a `FILE_*.md` vault card for each safe, previously-unseen file.

#### Module-level: Security Blacklist

```python
BLACKLIST_PATTERNS = [
    r"\.ssh", r"\.config", r"\.env", r"credentials",
    r"passwords?", r"secret", r"private[_\-]?key",
    r"id_rsa", r"\.pem", r"\.p12", r"\.pfx",
]
```

These regex patterns are compiled into `_BLACKLIST_RE` and checked against the
full file path. Any match causes the file to be silently skipped.

#### Function: `_is_safe(path)`

```python
def _is_safe(path: Path) -> bool
```

Returns `False` (skip) if the file:
- Starts with `.` (hidden file)
- Starts with `~` (temp/lock file)
- Ends with `.tmp` or `.part`
- Matches any pattern in `_BLACKLIST_RE`

#### Class: `FileWatcher(BaseWatcher)`

```python
class FileWatcher(BaseWatcher):
    def __init__(
        self,
        vault_path: str | Path,
        watch_dir: str | Path | None = None,
        check_interval: int = 60,
    )
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vault_path` | — | Path to vault root |
| `watch_dir` | `~/Downloads/file_check` | Directory to scan for new files |
| `check_interval` | `60` | Seconds between scans |

**`_seen_paths`** — `set[Path]` — in-memory deduplication set. Files added
here on first detection are never re-reported in the same session.

#### `check_for_updates() -> list[dict]`

Iterates `watch_dir`, filters via `_is_safe()` and `_already_logged()`, and
returns a list of item dicts for unseen files.

**Item dict schema:**

| Key | Type | Description |
|-----|------|-------------|
| `path` | `Path` | Absolute path to the file |
| `name` | `str` | Filename with extension |
| `suffix` | `str` | Lowercase extension, e.g. `".pdf"` |
| `size_bytes` | `int` | File size in bytes |
| `detected_at` | `datetime` | UTC timestamp of detection |

#### `create_action_file(item) -> Path`

Writes `Vault/Inbox/FILE_YYYYMMDD_HHMMSS_<slug>.md` with YAML frontmatter and
suggested actions checklist. Returns the path of the created card.

**Frontmatter fields written:**

| Field | Example |
|-------|---------|
| `type` | `file` |
| `file_name` | `"report.pdf"` |
| `file_path` | `"/home/user/Downloads/report.pdf"` |
| `file_size` | `"1230.4 KB"` |
| `file_type` | `".pdf"` |
| `detected_at` | `"2026-04-05 14:30:22 UTC"` |
| `priority` | `high` or `normal` |
| `status` | `pending` |

#### `post_cycle(created_count)`
Calls `update_activity`, `update_component_status` (`"File Monitor"`),
`update_stats` (increments `files_monitored`), and `refresh_vault_counts`.

#### Helper: `_already_logged(path, vault_path) -> bool`
Checks `Inbox/`, `Needs_Action/`, and `Done/` for any `.md` file whose name
contains the slug of `path`. Returns `True` if found (duplicate).

#### Helper: `_safe_slug(text, max_len=40) -> str`
Strips special characters, collapses whitespace to `_`, and truncates to
`max_len`. Used to build safe filenames from arbitrary file names.

#### Helper: `_infer_priority(name, suffix) -> str`
Returns `"high"` for `.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.zip`,
`.exe`, `.dmg`, or if the filename contains `urgent`, `invoice`, `contract`,
`payment`, or `asap`. Returns `"normal"` otherwise.

#### Helper: `_suggested_actions(suffix) -> str`
Returns a markdown checklist of suggested actions for the given file extension.
Falls back to a generic 3-item checklist for unknown extensions.

---

### 3.3 gmail_watcher.py

**Path:** `watchers/gmail_watcher.py`
**Purpose:** Polls Gmail using the official Gmail API. Finds unread emails in
inbox or important that match priority keywords, then creates `EMAIL_*.md` vault
cards.

#### Module-level constants

| Name | Value | Description |
|------|-------|-------------|
| `SCOPES` | `["gmail.readonly"]` | OAuth2 permission scope — read-only |
| `KEYWORDS` | `["urgent", "asap", "invoice", "payment"]` | Gmail search terms |
| `DEFAULT_CREDENTIALS_DIR` | `<project>/.credentials` | Default location for OAuth files |

#### Class: `GmailWatcher(BaseWatcher)`

```python
class GmailWatcher(BaseWatcher):
    def __init__(
        self,
        vault_path: str | Path,
        credentials_dir: str | Path | None = None,
        check_interval: int = 300,
        max_results: int = 20,
    )
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vault_path` | — | Path to vault root |
| `credentials_dir` | `DEFAULT_CREDENTIALS_DIR` | Folder with `credentials.json` |
| `check_interval` | `300` | Seconds between Gmail polls |
| `max_results` | `20` | Maximum emails to fetch per query |

**`_seen_ids`** — `set[str]` — in-memory set of Gmail message IDs already
processed this session.

#### `_get_service()` (internal)

Authentication flow:
1. Load `token.json` if it exists
2. If token is expired but has a refresh token → auto-refresh via `Request()`
3. If no valid token → run `InstalledAppFlow` (opens browser, one-time only)
4. Save refreshed/new token back to `token.json`
5. Return authenticated `googleapiclient` service object

Raises `FileNotFoundError` if `credentials.json` is missing.

#### `check_for_updates() -> list[dict]`

Builds the Gmail query via `_build_query()`, calls
`service.users().messages().list()`, then fetches metadata for each new
message. Skips messages in `_seen_ids` or already logged in the vault.

**Gmail query format:**
```
is:unread (label:inbox OR label:important) ("urgent" OR "asap" OR "invoice" OR "payment")
```

**Item dict schema:**

| Key | Type | Description |
|-----|------|-------------|
| `id` | `str` | Gmail message ID (unique, used for deduplication) |
| `subject` | `str` | Email subject line |
| `sender` | `str` | `From:` header value |
| `snippet` | `str` | First 200 characters of email body |
| `internal_date_ms` | `str` | Gmail's internal timestamp in milliseconds |

#### `create_action_file(item) -> Path`

Writes `Vault/Inbox/EMAIL_YYYYMMDD_HHMMSS_<msgid>.md` with YAML frontmatter
and suggested actions checklist. Returns the created card path.

**Frontmatter fields written:**

| Field | Example |
|-------|---------|
| `type` | `email` |
| `from` | `"billing@vendor.com"` |
| `subject` | `"Invoice for April services"` |
| `received` | `"2026-04-05 14:30:55 UTC"` |
| `priority` | `high` or `normal` |
| `status` | `pending` |
| `message_id` | `"1a2b3c4d5e6f7a8b"` |

#### `post_cycle(created_count)`
Calls `update_activity`, `update_component_status` (`"Gmail Monitor"`),
`update_stats` (increments `emails_checked`), and `refresh_vault_counts`.

#### Helper: `_build_query() -> str`
Constructs the Gmail search string from `KEYWORDS`. Each keyword is wrapped in
quotes and joined with `OR`.

#### Helper: `_already_logged(message_id, vault_path) -> bool`
Checks `Inbox/`, `Needs_Action/`, and `Done/` for any `.md` file whose name
contains `message_id`. Returns `True` if found.

#### Helper: `_parse_date(internal_date_ms) -> tuple[str, str]`
Converts Gmail's millisecond timestamp to a `(ISO string, slug string)` tuple:
- `"2026-04-05 14:30:55 UTC"` — for frontmatter
- `"20260405_143055"` — for the card filename

#### Helper: `_infer_priority(subject, snippet) -> str`
Returns `"high"` if `urgent` or `asap` appears in the combined text.
Returns `"normal"` otherwise (invoices/payments are normal priority with a
finance action checklist).

#### Helper: `_suggested_actions(subject, snippet) -> str`
Returns a finance-specific checklist for invoice/payment emails, an urgency
checklist for urgent/asap emails, or a generic checklist otherwise.

---

## 4. Helpers

### 4.1 dashboard_updater.py

**Path:** `helpers/dashboard_updater.py`
**Purpose:** All read/write operations on `Dashboard.md`. Four public functions
cover the full set of dashboard updates the system ever needs to make.

#### Module-level constants

```python
MAX_ACTIVITY_ENTRIES = 20   # Activity log is capped at this many entries
```

**`STAT_LABELS`** — maps internal stat key → display label in the Quick Stats
table:

| Key | Label in Dashboard.md |
|-----|-----------------------|
| `files_monitored` | `Files monitored` |
| `emails_checked` | `Emails checked` |
| `tasks_in_inbox` | `Tasks in Inbox` |
| `tasks_in_needs_action` | `Tasks in Needs_Action` |
| `tasks_completed` | `Tasks completed` |

**`COMPONENT_NAMES`** — maps lowercase component name → display name in the
System Status table:

| Key | Display Name |
|-----|-------------|
| `file monitor` | `File Monitor` |
| `gmail monitor` | `Gmail Monitor` |
| `dashboard updater` | `Dashboard Updater` |
| `inbox processor` | `Inbox Processor` |

**`STATUS_DISPLAY`** — maps code status → display string:

| Input | Output |
|-------|--------|
| `running`, `online` | `ONLINE` |
| `offline`, `not running` | `OFFLINE` |
| `error` | `ERROR` |
| `ready` | `READY` |

#### Internal helpers

**`_dashboard_path(vault_path)`** — Returns `Path(vault_path) / "Dashboard.md"`.

**`_read(vault_path)`** — Reads and returns `Dashboard.md` as a string. Raises
`FileNotFoundError` if missing.

**`_write(vault_path, content)`** — Writes string back to `Dashboard.md`.

**`_stamp(content)`** — Removes all existing `_Last updated:_` lines and
inserts one with the current timestamp immediately after the first heading.

**`_find_section(content, header)`** — Returns `(start, end)` character
indices of the section body following `header`, up to the next heading of the
same or higher level.

---

#### `update_activity(vault_path, message)`

```python
def update_activity(vault_path: str | Path, message: str) -> None
```

Prepends a timestamped entry to the `## Recent Activity` section and trims
the list to `MAX_ACTIVITY_ENTRIES` (20).

**Entry format:** `` - `YYYY-MM-DD HH:MM` -- <message> ``

**Example:**
```python
update_activity(vault_path, "File Monitor: 3 new file(s) detected")
```

---

#### `update_stats(vault_path, stat_name, value, operation='set')`

```python
def update_stats(
    vault_path: str | Path,
    stat_name: str,
    value: int,
    operation: str = "set",
) -> None
```

Finds the stat row in the `## Quick Stats` table and updates its numeric value.

| Parameter | Values | Description |
|-----------|--------|-------------|
| `stat_name` | See `STAT_LABELS` | Which stat to update |
| `value` | Any `int` | The value to set or add |
| `operation` | `"set"` or `"increment"` | How to apply the value |

When `operation="increment"`, the result is clamped to a minimum of 0.

**Example:**
```python
update_stats(vault_path, "files_monitored", 3, "increment")
update_stats(vault_path, "tasks_in_inbox", 0, "set")
```

---

#### `update_component_status(vault_path, component, status, notes='')`

```python
def update_component_status(
    vault_path: str | Path,
    component: str,
    status: str,
    notes: str = "",
) -> None
```

Finds the component row in the `## System Status` table and rewrites it with
the new status, current timestamp, and optional notes.

Component names are matched case-insensitively with prefix/substring fallback.
If `notes` is empty: writes `"—"` for offline components and `"OK"` for online.

**Example:**
```python
update_component_status(vault_path, "Gmail Monitor", "online")
update_component_status(vault_path, "Inbox Processor", "error", "Parse failed")
```

---

#### `refresh_vault_counts(vault_path)`

```python
def refresh_vault_counts(vault_path: str | Path) -> None
```

Counts `.md` files in `Inbox/`, `Needs_Action/`, and `Done/`, then calls
`update_stats` with `operation="set"` to sync `tasks_in_inbox`,
`tasks_in_needs_action`, and `tasks_completed` to accurate values.

**Example:**
```python
refresh_vault_counts(vault_path)
# Output: Vault counts synced: inbox=0, needs_action=6, done=3
```

---

#### CLI usage

```bash
# Log an activity entry
python helpers/dashboard_updater.py --activity "File monitor: 2 new files"

# Set a stat
python helpers/dashboard_updater.py --stat files_monitored --value 5

# Increment a stat
python helpers/dashboard_updater.py --stat emails_checked --value 1 --operation increment

# Update component status
python helpers/dashboard_updater.py --component "File Monitor" --status running
python helpers/dashboard_updater.py --component "Gmail Monitor" --status offline
python helpers/dashboard_updater.py --component "Inbox Processor" --status error --notes "Parse error"

# Resync all vault counts
python helpers/dashboard_updater.py --refresh-counts

# Custom vault path
python helpers/dashboard_updater.py --vault /path/to/vault --refresh-counts
```

---

### 4.2 inbox_processor.py

**Path:** `helpers/inbox_processor.py`
**Purpose:** Reads every `.md` card in `Vault/Inbox/`, applies routing rules
based on frontmatter, and moves each card to `Needs_Action/` or `Done/`.

#### Module-level extension sets

| Variable | Extensions | Action |
|----------|-----------|--------|
| `DOCUMENT_EXTENSIONS` | `.pdf .doc .docx .txt .md .csv .xlsx .xls` | → `Needs_Action/` |
| `IMAGE_EXTENSIONS` | `.png .jpg .jpeg .gif .webp .svg` | → `Needs_Action/` |
| `ARCHIVE_EXTENSIONS` | `.zip .tar .gz .rar .7z` | → `Needs_Action/` |
| `EXEC_EXTENSIONS` | `.exe .msi .dmg .pkg .sh` | → `Needs_Action/` (flagged) |
| `DISCARD_EXTENSIONS` | `.tmp .temp .bak` | → `Done/` (auto-discard) |
| `DISCARD_NAME_HINTS` | `["test", "temp", "delete"]` | → `Done/` (auto-discard) |

#### `process_inbox(vault_path) -> dict`

```python
def process_inbox(vault_path: str | Path) -> dict
```

Main entry point. Processes all cards in `Inbox/`.

**Returns:**

```python
{
    "processed":       int,   # total cards handled
    "to_needs_action": int,   # cards moved to Needs_Action/
    "to_done":         int,   # cards moved to Done/
    "errors":          list,  # list of (filename, error_message) tuples
}
```

**Process:**
1. List all `.md` files in `Inbox/` (sorted alphabetically)
2. Parse YAML frontmatter via `python-frontmatter`
3. Apply routing rules (`_route()`)
4. Move file via `_move()` — handles filename conflicts with `_1`, `_2` suffixes
5. Call `update_activity`, `refresh_vault_counts`,
   `update_component_status("Inbox Processor", "online")` after all cards

#### `_route(post, card_path) -> tuple[str, str]`

Dispatches to `_route_file` or `_route_email` based on the card's `type`
frontmatter field.

Returns `("needs_action" | "done", reason_string)`.

#### `_route_file(post, card_path) -> tuple[str, str]`

Reads `file_type` and `file_name` from frontmatter and applies the extension
and name-hint rules. Returns destination and a human-readable reason string.

#### `_route_email(post) -> tuple[str, str]`

All emails return `("needs_action", reason)`. Reason varies by priority and
subject keywords but the destination is always `Needs_Action/`.

#### `_move(src, dest_dir) -> Path`

```python
def _move(src: Path, dest_dir: Path) -> Path
```

Moves `src` to `dest_dir` using `shutil.move`. Creates `dest_dir` if it does
not exist. Appends `_1`, `_2`, ... to the stem if a filename conflict exists.
Returns the final destination path.

---

#### CLI usage

```bash
python helpers/inbox_processor.py
python helpers/inbox_processor.py --vault /path/to/AI_Employee_Vault
```

Exits with code `1` if any errors occurred during processing.

---

## 5. Claude Agent Skills

Skills are plain Markdown files in `.claude/skills/*/SKILL.md`. Claude Code
reads them on invocation and executes the embedded instructions.

### 5.1 file-monitor

**Path:** `.claude/skills/file-monitor/SKILL.md`
**Trigger phrases:** `"check for new files"`, `"monitor downloads"`,
`"scan downloads"`, `"check downloads folder"`

**What it does:**
1. Imports `FileWatcher` from `watchers.file_watcher`
2. Instantiates `FileWatcher(vault_path=<vault>, watch_dir=~/Downloads/file_check)`
3. Calls `check_for_updates()` once — no loop
4. Calls `create_action_file(item)` for each new file
5. Calls the `update-dashboard` skill after all cards are created

**Config (frontmatter):**

```yaml
config:
  monitored_folders:
    - ~/Downloads/file_check
  ignored_patterns:
    - .ssh
    - .config
    - .env
    - credentials
    - passwords
```

**Output cards:** `Vault/Inbox/FILE_YYYYMMDD_HHMMSS_<slug>.md`

---

### 5.2 gmail-monitor

**Path:** `.claude/skills/gmail-monitor/SKILL.md`
**Trigger phrases:** `"check gmail"`, `"check my email"`, `"scan inbox"`,
`"monitor email"`

**What it does:**
1. Imports `GmailWatcher` from `watchers.gmail_watcher`
2. Instantiates `GmailWatcher(vault_path=<vault>)`
3. Authenticates (reuses `token.json`, auto-refreshes, or opens browser)
4. Calls `check_for_updates()` once — runs the Gmail query
5. Calls `create_action_file(item)` for each new priority email
6. Calls the `update-dashboard` skill after all cards are created

**Config (frontmatter):**

```yaml
config:
  scopes:
    - https://www.googleapis.com/auth/gmail.readonly
  keywords:
    - urgent
    - asap
    - invoice
    - payment
  credentials_dir: ~/Desktop/Hackathon/Hackathon0/ai-employee-project/.credentials
```

**Output cards:** `Vault/Inbox/EMAIL_YYYYMMDD_HHMMSS_<msgid>.md`

---

### 5.3 process-inbox

**Path:** `.claude/skills/process-inbox/SKILL.md`
**Trigger phrases:** `"process inbox"`, `"check inbox"`, `"triage tasks"`,
`"what's in inbox"`

**What it does:**
1. Imports `process_inbox` from `helpers.inbox_processor`
2. Calls `process_inbox(vault_path)` — processes all cards in one pass
3. Prints the summary returned from `process_inbox`

**Routing rules (summary):**

| Card type | Condition | Destination |
|-----------|-----------|-------------|
| `file` | Extension in `DISCARD_EXTENSIONS` | `Done/` |
| `file` | Name contains `test`, `temp`, `delete` | `Done/` |
| `file` | Any other extension | `Needs_Action/` |
| `email` | Any | `Needs_Action/` |
| unknown | Any | `Needs_Action/` |

---

### 5.4 update-dashboard

**Path:** `.claude/skills/update-dashboard/SKILL.md`
**Trigger phrases:** `"update dashboard"`, `"refresh dashboard"`,
`"log activity"`, `"update stats"`

**What it does:**
Calls one or more of the four functions from `helpers.dashboard_updater`:

| Operation | Function called |
|-----------|----------------|
| Log an activity entry | `update_activity(vault_path, message)` |
| Update a stat counter | `update_stats(vault_path, stat_name, value, operation)` |
| Update component status | `update_component_status(vault_path, component, status)` |
| Resync all vault counts | `refresh_vault_counts(vault_path)` |

**Always called as the final step by all other skills.**

---

## 6. External Tools & Libraries

### Python Standard Library

| Module | Used in | Purpose |
|--------|---------|---------|
| `pathlib.Path` | All files | Cross-platform path handling |
| `re` | `file_watcher.py`, `dashboard_updater.py` | Regex matching for blacklist, slug generation, table row edits |
| `datetime` | `file_watcher.py`, `gmail_watcher.py`, `dashboard_updater.py` | Timestamps on cards and dashboard |
| `threading` | `main.py` | Daemon threads for each watcher |
| `logging` | `main.py`, `base_watcher.py` | Structured log output to file and console |
| `argparse` | `main.py`, helpers | CLI argument parsing |
| `shutil` | `inbox_processor.py` | `shutil.move()` to move vault cards |
| `signal` | `main.py` | Graceful shutdown on SIGINT/SIGTERM |
| `abc` | `base_watcher.py` | `ABC`, `abstractmethod` for interface enforcement |
| `sys` | All files | `sys.path` manipulation for imports |
| `time` | `base_watcher.py` | `time.sleep()` for poll intervals |

---

### Third-Party Libraries

#### `watchdog` (v6.0.0)
- **Declared in:** `pyproject.toml`
- **Used in:** Listed as a dependency; the current implementation uses direct
  directory iteration (`Path.iterdir()`) rather than filesystem event callbacks.
  Retained for potential Silver Tier live monitoring upgrade.
- **Install:** `pip install watchdog`

#### `python-frontmatter` (v1.1.0)
- **Used in:** `helpers/inbox_processor.py`
- **Purpose:** Parses YAML frontmatter from `.md` vault cards
- **Key call:** `frontmatter.load(str(card_path))` → returns a `Post` object
  with `.get("field_name")` for frontmatter access and `.content` for the body
- **Install:** `pip install python-frontmatter`

#### `google-api-python-client` (v2.193.0)
- **Used in:** `watchers/gmail_watcher.py`
- **Purpose:** Official Google API client. Builds the Gmail API service object
- **Key call:** `build("gmail", "v1", credentials=creds)` → returns a service
  object used for all Gmail API calls
- **API calls made:**
  - `service.users().messages().list(userId="me", q=query, maxResults=n).execute()`
  - `service.users().messages().get(userId="me", id=msg_id, format="metadata", metadataHeaders=["From","Subject"]).execute()`
- **Install:** `pip install google-api-python-client`

#### `google-auth-oauthlib` (v1.3.1)
- **Used in:** `watchers/gmail_watcher.py`
- **Purpose:** Handles the OAuth2 browser-based authorisation flow
- **Key call:** `InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES).run_local_server(port=0)`
- **Install:** `pip install google-auth-oauthlib`

#### `google-auth-httplib2` (v0.3.1)
- **Used in:** `watchers/gmail_watcher.py`
- **Purpose:** HTTP transport layer for Google auth; required by
  `google-api-python-client` when refreshing tokens
- **Key call:** `creds.refresh(Request())` — `Request` from
  `google.auth.transport.requests`
- **Install:** `pip install google-auth-httplib2`

---

### Google APIs

#### Gmail API (v1)
- **Scope used:** `https://www.googleapis.com/auth/gmail.readonly`
- **Endpoints called:**

| Method | What it does |
|--------|-------------|
| `users.messages.list` | Search Gmail with a query string, returns message IDs |
| `users.messages.get` | Fetch metadata (From, Subject) for a message ID |

- **Query format:** `is:unread (label:inbox OR label:important) ("urgent" OR "asap" OR "invoice" OR "payment")`
- **Auth type:** OAuth 2.0, Desktop application
- **Credentials files:** `.credentials/credentials.json` (app identity),
  `.credentials/token.json` (user access token, auto-refreshed)

---

## 7. Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md          ← Live status dashboard (auto-updated)
├── Company_Handbook.md   ← Monitoring rules and policies
├── Inbox/                ← New cards land here (FILE_*.md, EMAIL_*.md)
├── Needs_Action/         ← Cards requiring human follow-up
└── Done/                 ← Resolved/auto-discarded cards (audit trail)
```

### Dashboard.md sections

| Section | Updated by | Frequency |
|---------|-----------|-----------|
| `## System Status` | `update_component_status()` | After each watcher cycle |
| `## Quick Stats` | `update_stats()`, `refresh_vault_counts()` | After each cycle |
| `## Recent Activity` | `update_activity()` | After each cycle (max 20 entries) |
| `_Last updated:_` | `_stamp()` | Every write to Dashboard.md |

### Card filename conventions

| Prefix | Source | Filename pattern |
|--------|--------|-----------------|
| `FILE_` | FileWatcher | `FILE_YYYYMMDD_HHMMSS_<slug>.md` |
| `EMAIL_` | GmailWatcher | `EMAIL_YYYYMMDD_HHMMSS_<msgid>.md` |

The Gmail message ID embedded in `EMAIL_` filenames is the deduplication key —
never rename email cards manually.

---

## 8. Configuration Reference

### Changing the watched folder (file-monitor)

1. Edit `watchers/file_watcher.py`:
   ```python
   self.watch_dir = Path(watch_dir) if watch_dir else Path.home() / "Downloads/your-folder"
   ```
2. Or pass `watch_dir` explicitly:
   ```python
   FileWatcher(vault_path=vault, watch_dir="/path/to/folder")
   ```
3. Update the `config.monitored_folders` entry in `.claude/skills/file-monitor/SKILL.md`.

### Adding Gmail keywords

1. Edit `watchers/gmail_watcher.py`:
   ```python
   KEYWORDS = ["urgent", "asap", "invoice", "payment", "contract"]
   ```
2. Update `config.keywords` in `.claude/skills/gmail-monitor/SKILL.md`.

### Changing poll intervals

Pass `--file-interval` and `--gmail-interval` to `main.py`:
```bash
python main.py --file-interval 30 --gmail-interval 60
```

Or modify the defaults in `_parse_args()` in `main.py`.

### Adding a stat to the dashboard

1. Add a row to the `## Quick Stats` table in `Dashboard.md`
2. Add the key → label mapping to `STAT_LABELS` in `dashboard_updater.py`
3. Call `update_stats(vault_path, "new_stat_key", value)` from the relevant watcher

### Adding a new component to the System Status table

1. Add a row to the `## System Status` table in `Dashboard.md`
2. Add the lowercase key → display name to `COMPONENT_NAMES` in `dashboard_updater.py`
3. Call `update_component_status(vault_path, "New Component", "online")` from the component

---

## 9. Data Flow

```
User trigger  ─────────────────────────────────────────────────────────────►
                                                                             │
               ┌─────────────────────────────────────────────────────────┐  │
               │  Claude Code reads SKILL.md  (trigger phrase matched)  │◄─┘
               └──────────────────────┬──────────────────────────────────┘
                                       │
               ┌───────────────────────▼────────────────────────────────┐
               │  FileWatcher.check_for_updates()                       │
               │    • Iterates ~/Downloads/file_check                   │
               │    • Filters via _is_safe() + _already_logged()       │
               │    • Returns list[dict] of new files                   │
               └───────────────────────┬────────────────────────────────┘
                                       │  OR
               ┌───────────────────────▼────────────────────────────────┐
               │  GmailWatcher.check_for_updates()                      │
               │    • Authenticates via OAuth token.json                │
               │    • Queries Gmail API with keyword filter             │
               │    • Returns list[dict] of new priority emails         │
               └───────────────────────┬────────────────────────────────┘
                                       │
                                       ▼
               ┌────────────────────────────────────────────────────────┐
               │  create_action_file(item)                              │
               │    • Builds YAML frontmatter                           │
               │    • Writes FILE_*.md / EMAIL_*.md to Vault/Inbox/    │
               └───────────────────────┬────────────────────────────────┘
                                       │
                                       ▼
               ┌────────────────────────────────────────────────────────┐
               │  update-dashboard skill                                │
               │    • update_activity()  — log the event               │
               │    • update_component_status()  — mark ONLINE         │
               │    • update_stats()  — increment counter              │
               │    • refresh_vault_counts()  — resync folder counts   │
               └───────────────────────┬────────────────────────────────┘
                                       │   (later, user triggers process-inbox)
                                       ▼
               ┌────────────────────────────────────────────────────────┐
               │  process_inbox(vault_path)                             │
               │    • Read each card in Inbox/                         │
               │    • Parse frontmatter via python-frontmatter         │
               │    • Apply routing rules (_route_file / _route_email) │
               │    • Move to Needs_Action/ or Done/                   │
               │    • refresh_vault_counts()                            │
               └────────────────────────────────────────────────────────┘
```

---

## 10. Error Handling Patterns

### File watcher — missing watch directory
```python
if not self.watch_dir.exists():
    self.logger.warning(f"Watch directory not found: {self.watch_dir}")
    return []
```
Returns empty list — does not crash the poll loop.

### Gmail watcher — network failure during token refresh
```python
except TransportError as e:
    self.logger.error(f"Token refresh failed (network error): {e}")
    raise
```
Raises to the orchestrator thread, which logs the error and schedules a restart.

### Gmail watcher — missing credentials file
```python
raise FileNotFoundError(
    f"credentials.json not found at {self.credentials_file}\n"
    "Download it from Google Cloud Console → APIs & Services → Credentials."
)
```
Raised at init time — caught by `WatcherThread._run_loop()`, logged, and the
thread exits (no restart until next health check cycle).

### Inbox processor — frontmatter parse failure
```python
try:
    post = frontmatter.load(str(card))
except Exception as e:
    summary["errors"].append((card.name, str(e)))
    continue
```
Logs the error and skips to the next card — the entire run continues.

### Dashboard updater — missing section header
```python
except ValueError as e:
    print(f"[dashboard-updater] WARNING: {e}")
    return
```
Logs a warning and returns — the dashboard write is skipped rather than
crashing the watcher that called it.

### Orchestrator — crashed watcher thread
```python
if not wt.is_alive and not self._shutdown.is_set():
    self.logger.warning(f"{wt.name} is not alive — restarting...")
    wt.start()
```
Health-checks run every 5 minutes. Any dead thread is restarted automatically.

---

*Documentation covers AI Employee Bronze Tier — build date 2026-04-06.*
