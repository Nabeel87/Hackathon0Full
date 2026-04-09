# AI Employee — Bronze Tier
## Complete System Documentation

> An autonomous, privacy-respecting AI employee that monitors your files and
> inbox, creates structured task cards, and keeps a live dashboard — all
> running locally with zero cloud infrastructure.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Components Deep Dive](#3-components-deep-dive)
4. [Tools & Technologies](#4-tools--technologies)
5. [Privacy & Security](#5-privacy--security)
6. [Configuration](#6-configuration)
7. [How It Works — Complete Example](#7-how-it-works--complete-example)
8. [Error Handling](#8-error-handling)
9. [Limitations & Known Issues](#9-limitations--known-issues)
10. [Future Enhancements](#10-future-enhancements)
11. [Troubleshooting](#11-troubleshooting)
12. [References](#12-references)

---

## 1. Project Overview

### What Is This Project?

AI Employee is a local automation system that acts as a tireless digital
assistant. It monitors your file system and Gmail inbox, converts every new
file or priority email into a structured task card, and maintains a live
operational dashboard — all without any server, scheduler, or cloud dependency.

### What Problem Does It Solve?

Professionals constantly miss important files and emails because they arrive
silently while attention is elsewhere. Manual inbox triage is repetitive and
error-prone. AI Employee eliminates both problems by:

- Detecting new files and emails the moment they arrive
- Converting them into actionable, structured task cards automatically
- Surfacing everything in a single dashboard you can open in Obsidian
- Enforcing a consistent `Inbox → Needs_Action → Done` workflow

### Key Features

- **Autonomous monitoring** — watches `~/Downloads` and Gmail continuously in
  parallel threads; no manual triggers needed
- **Privacy by design** — read-only Gmail access, no file contents ever read,
  credentials never leave your machine, full blacklist of sensitive patterns
- **Structured vault** — every detected item becomes a Markdown card with YAML
  frontmatter, priority inference, and a suggested-actions checklist
- **Live dashboard** — `Dashboard.md` tracks system status, counters, and a
  20-entry timestamped activity log, updated after every event

### Architecture Approach

The system is built on two complementary layers:

| Layer | What it is | Role |
|-------|-----------|------|
| **Agent Skills** | Plain Markdown files in `.claude/skills/` | Claude reads these to understand what to do and which Python code to call. No logic lives here — only instructions. |
| **Python Watchers & Helpers** | Scripts in `watchers/` and `helpers/` | The actual logic: polling, API calls, file I/O, dashboard writes. Run directly or called by the orchestrator. |

Skills are human-readable, version-controlled, and editable without touching
Python. The Python layer is clean, tested, and importable independently.

### Bronze Tier Scope

Bronze is the **minimal viable AI Employee** — a fully working foundation:

- Two input streams (file system + Gmail)
- One vault pipeline (`Inbox → Needs_Action → Done`)
- One live dashboard
- Four agent skills + one meta-skill for creating more
- Runs on-demand via Claude Code or continuously via the orchestrator

It does not include scheduling, outbound communication, approvals, or
third-party integrations — those are Silver and Gold tier features.

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AGENT SKILLS LAYER                           │
│   .claude/skills/                                                   │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐ │
│   │ file-monitor │ │gmail-monitor │ │process-inbox │ │dashboard │ │
│   │  SKILL.md    │ │  SKILL.md    │ │  SKILL.md    │ │ SKILL.md │ │
│   └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────┬─────┘ │
└──────────┼────────────────┼────────────────┼───────────────┼───────┘
           │                │                │               │
           ▼                ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PYTHON CODE LAYER                             │
│                                                                     │
│  ┌─────────────────────┐     ┌──────────────────────────────────┐  │
│  │   watchers/         │     │   helpers/                       │  │
│  │                     │     │                                  │  │
│  │  base_watcher.py    │     │  dashboard_updater.py            │  │
│  │  file_watcher.py    │     │  inbox_processor.py              │  │
│  │  gmail_watcher.py   │     │                                  │  │
│  └──────────┬──────────┘     └───────────────┬──────────────────┘  │
│             │                                │                     │
│             └──────────────┬─────────────────┘                     │
│                            │                                       │
│                     ┌──────▼──────┐                                │
│                     │   main.py   │  ← Orchestrator                │
│                     │ (threads +  │                                │
│                     │  restarts)  │                                │
│                     └─────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
           │                │
           ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                 │
│                                                                     │
│  INPUTS                              VAULT (AI_Employee_Vault/)     │
│  ──────                              ─────────────────────────────  │
│                                                                     │
│  ~/Downloads/file_check/  ────────►  Inbox/       FILE_*.md        │
│  (new files)                                      EMAIL_*.md        │
│                                            │                        │
│  Gmail Inbox              ────────►        ▼                        │
│  (unread, keywords)                  Needs_Action/  (human review)  │
│                                            │                        │
│                                            ▼                        │
│  Dashboard.md  ◄── all components    Done/          (audit trail)   │
│  (live status)                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Folder Structure

```
ai-employee-project/
│
├── .claude/                    # Claude Code configuration
│   └── skills/                 # Agent Skills — instruction-only Markdown files
│       ├── file-monitor/
│       │   └── SKILL.md        # Instructions for scanning ~/Downloads
│       ├── gmail-monitor/
│       │   └── SKILL.md        # Instructions for checking Gmail inbox
│       ├── process-inbox/
│       │   └── SKILL.md        # Instructions for routing Inbox cards
│       ├── update-dashboard/
│       │   └── SKILL.md        # Instructions for refreshing Dashboard.md
│       └── skill-creator/
│           └── SKILL.md        # Meta-skill: creates new skills from a template
│
├── watchers/                   # Python polling scripts
│   ├── __init__.py
│   ├── base_watcher.py         # Abstract base class — shared polling loop
│   ├── file_watcher.py         # Watches a directory for new files
│   └── gmail_watcher.py        # Queries Gmail API for priority emails
│
├── helpers/                    # Python utility scripts
│   ├── __init__.py
│   ├── dashboard_updater.py    # Reads and writes Dashboard.md
│   └── inbox_processor.py      # Routes Inbox cards to Needs_Action or Done
│
├── documents/                  # Project documentation
│   ├── GMAIL_SETUP.md          # Step-by-step Gmail API setup guide
│   ├── BRONZE_COMPLETE.md      # Milestone notes
│   ├── CODE_DOCUMENTATION.md   # Full technical API reference
│   └── DEPLOYMENT_GUIDE.md     # New-machine deployment walkthrough
│
├── .credentials/               # OAuth credentials (git-ignored)
│   ├── credentials.json        # OAuth app identity from Google Cloud Console
│   └── token.json              # Personal access token (auto-created on first run)
│
├── logs/                       # Runtime logs
│   └── main.log                # Rolling log file from orchestrator
│
├── main.py                     # Master orchestrator — runs all watchers in threads
├── pyproject.toml              # Project metadata and dependency declarations
├── requirements.txt            # Pinned dependency versions
├── README.md                   # Quick-start guide
├── DOCUMENTATION.md            # This file
└── .gitignore                  # Excludes .env, .credentials/, .venv/, logs/
```

**Folder explanations:**

| Folder | Purpose |
|--------|---------|
| `.claude/skills/` | Plain Markdown instruction files. Claude reads these when you type a trigger phrase. Contains no Python — only natural language descriptions of what to do and which Python module to call. |
| `watchers/` | Python polling scripts. Each watcher checks one input source (filesystem or Gmail), builds item dicts for new items, and writes vault cards. All watchers inherit from `base_watcher.py`. |
| `helpers/` | Utility scripts called by watchers and the orchestrator. `dashboard_updater.py` owns all writes to `Dashboard.md`. `inbox_processor.py` owns all Inbox triage logic. |
| `documents/` | Reference documentation — setup guides, API reference, deployment instructions. Not read by the running system. |
| `.credentials/` | Gmail OAuth files. Never committed to git. Created by the Gmail setup process. |
| `logs/` | Text logs from the orchestrator. `main.log` captures all watcher output with timestamps. |

### 2.3 Data Flow

```
1. DETECTION
   ──────────
   New file appears in ~/Downloads/file_check/
         │
         ▼
   file_watcher.py → check_for_updates()
   • Iterates directory
   • _is_safe() filters hidden files, temp files, blacklisted patterns
   • _already_logged() skips files with existing vault cards
   • Returns list of new file metadata dicts
         │
         ▼ (simultaneously, in a separate thread)
   gmail_watcher.py → check_for_updates()
   • Authenticates via token.json
   • Queries: is:unread (label:inbox OR label:important) ("urgent" OR ...)
   • Returns list of new email metadata dicts

2. TASK CREATION
   ──────────────
   For each item dict →  create_action_file(item)
   • Builds YAML frontmatter (type, name, path/sender, priority, status)
   • Infers priority from filename/subject keywords
   • Appends suggested-actions checklist
   • Writes FILE_*.md or EMAIL_*.md to AI_Employee_Vault/Inbox/

3. DASHBOARD UPDATE
   ─────────────────
   After each cycle with new cards:
   • update_activity()          → prepend timestamped entry to Recent Activity
   • update_component_status()  → mark component ONLINE with current timestamp
   • update_stats()             → increment files_monitored or emails_checked
   • refresh_vault_counts()     → recount Inbox/, Needs_Action/, Done/
   • _stamp()                   → update "Last updated" timestamp

4. TRIAGE (on demand)
   ───────────────────
   User says "process inbox" → process_inbox(vault_path)
   • Read each .md card in Inbox/
   • Parse YAML frontmatter via python-frontmatter
   • Apply routing rules:
       .tmp / .temp / .bak / name contains test|temp|delete → Done/
       all other files, all emails                           → Needs_Action/
   • Move file, handle filename conflicts
   • refresh_vault_counts() → sync dashboard counts

5. REVIEW
   ───────
   User opens AI_Employee_Vault/ in Obsidian
   • Dashboard.md shows live status, counters, activity log
   • Inbox/ shows unprocessed cards
   • Needs_Action/ shows cards awaiting human decision
   • Done/ shows resolved items (permanent audit trail)
```

---

## 3. Components Deep Dive

### 3.1 Agent Skills

Agent Skills are plain Markdown files that Claude Code reads as instructions.
They contain no Python code — only descriptions of what to do and which Python
modules to invoke. This makes them easy to read, edit, and version-control.

---

#### `file-monitor` — `.claude/skills/file-monitor/SKILL.md`

**Purpose:** Gives the AI employee visibility into files that arrive from
outside (downloads, shared files). Converts raw file arrivals into actionable
vault cards with suggested next steps.

**How it works:**
1. Imports `FileWatcher` from `watchers.file_watcher`
2. Instantiates with `vault_path` and `watch_dir=~/Downloads/file_check`
3. Calls `check_for_updates()` once (no loop)
4. Calls `create_action_file(item)` for each safe, new file
5. Calls `update-dashboard` skill after all cards are created

**Input:** Files present in `~/Downloads/file_check/` not already in the vault

**Output:** `AI_Employee_Vault/Inbox/FILE_YYYYMMDD_HHMMSS_<slug>.md`

**Trigger phrases:** `"check for new files"` · `"scan downloads"` · `"monitor downloads"`

```
Example output card filename:
FILE_20260406_143022_invoice_April_pdf.md
```

---

#### `gmail-monitor` — `.claude/skills/gmail-monitor/SKILL.md`

**Purpose:** Surfaces important emails (urgent requests, invoices, payments)
as actionable vault cards. Bridges Gmail and the vault pipeline so emails get
triaged alongside file tasks.

**How it works:**
1. Imports `GmailWatcher` from `watchers.gmail_watcher`
2. Authenticates via `token.json` (auto-refreshes; opens browser only on first run)
3. Queries Gmail: `is:unread (label:inbox OR label:important) ("urgent" OR "asap" OR "invoice" OR "payment")`
4. Calls `create_action_file(item)` for each unlogged priority email
5. Calls `update-dashboard` skill after all cards are created

**Input:** Unread Gmail messages matching keyword filter, not already in vault

**Output:** `AI_Employee_Vault/Inbox/EMAIL_YYYYMMDD_HHMMSS_<msgid>.md`

**Trigger phrases:** `"check gmail"` · `"check my email"` · `"scan inbox"`

```
Data stored per email:  sender, subject, 200-char snippet only
Data NEVER stored:      full email body, attachments, headers beyond From/Subject
```

---

#### `update-dashboard` — `.claude/skills/update-dashboard/SKILL.md`

**Purpose:** Keeps `Dashboard.md` accurate after every skill run. Provides a
timestamped activity log and live counters for the vault pipeline.

**How it works:** Calls one or more functions from `helpers.dashboard_updater`:

| Operation | Function | When used |
|-----------|----------|-----------|
| Log event | `update_activity(vault_path, msg)` | After any detection |
| Increment counter | `update_stats(vault_path, key, n, "increment")` | After new cards created |
| Mark component online | `update_component_status(vault_path, name, "online")` | After successful cycle |
| Resync counts | `refresh_vault_counts(vault_path)` | After bulk moves |

**Input:** Vault path + operation type + value

**Output:** Modified `Dashboard.md` with updated timestamp

**Trigger phrases:** `"update dashboard"` · `"refresh dashboard"` · `"update stats"`

---

#### `process-inbox` — `.claude/skills/process-inbox/SKILL.md`

**Purpose:** Clears the Inbox by routing every pending card to the correct
vault folder. Applies consistent business rules so nothing is misrouted.

**How it works:**
1. Imports `process_inbox` from `helpers.inbox_processor`
2. Calls `process_inbox(vault_path)` — processes all cards in a single pass
3. For each card: parse YAML frontmatter → apply routing rules → move file
4. Calls `refresh_vault_counts()` after all moves

**Input:** `.md` files in `AI_Employee_Vault/Inbox/`

**Output:** Cards moved to `Needs_Action/` or `Done/`; dashboard updated

**Routing rules:**

| Condition | Destination |
|-----------|-------------|
| Extension `.tmp` `.temp` `.bak` | `Done/` (auto-discard) |
| Filename contains `test`, `temp`, `delete` | `Done/` (auto-discard) |
| Documents, images, archives, executables | `Needs_Action/` |
| Any email (type=email) | `Needs_Action/` (never auto-discarded) |
| Unknown type | `Needs_Action/` (safe default) |

**Trigger phrases:** `"process inbox"` · `"triage tasks"` · `"check inbox"`

---

#### `skill-creator` — `.claude/skills/skill-creator/SKILL.md`

**Purpose:** Meta-skill that generates new Agent Skills following the project's
standard template. Enforces consistency across all skills — every generated
skill passes the same structural checklist.

**How it works:**
1. Asks the user 7 questions (skill name, description, triggers, input, output,
   Python module, API/credentials needed)
2. Generates a complete `SKILL.md` using the standard template
3. Validates against a checklist (no Python code, all sections present, correct
   naming conventions)
4. Saves to `.claude/skills/<skill-name>/SKILL.md`

**Input:** User answers to 7 questions about the new skill

**Output:** New `SKILL.md` at `.claude/skills/<name>/SKILL.md`

**Trigger phrases:** `"create skill"` · `"make new skill"` · `"add skill"`

```
Checklist enforced:
  ✓ Frontmatter has name, description, ≥2 triggers
  ✓ All sections present (Purpose, Process, How to Run, Output, Dependencies)
  ✓ No Python code anywhere in the file
  ✓ Trigger phrases are 2–5 words each
  ✓ Skill name is lowercase-hyphenated
```

---

### 3.2 Python Watchers

#### `base_watcher.py` — `watchers/base_watcher.py`

**Purpose:** Abstract base class that all watchers inherit from. Defines the
polling contract and provides a reusable polling loop.

**How it works:** Defines two abstract methods that every watcher must implement:

```python
check_for_updates() -> list[dict]   # check source, return new items
create_action_file(item) -> Path    # write vault card, return path
```

The `run()` method provides a complete polling loop: call `check_for_updates()`,
call `create_action_file()` for each item, call `post_cycle()` if cards were
created, sleep via `_interruptible_sleep()` (1-second ticks, responds to
`stop()` within 1 second).

**Input:** `vault_path` (vault root), `check_interval` (seconds)

**Output:** Runs indefinitely until `stop()` is called

---

#### `file_watcher.py` — `watchers/file_watcher.py`

**Purpose:** Scans a directory for new files and creates vault task cards.
Point-in-time snapshot per invocation — not a live inotify/kqueue watcher.

**How it works:**
1. Iterates `watch_dir` (default `~/Downloads/file_check`)
2. `_is_safe(path)` — rejects hidden files, temp files, any path matching the
   security blacklist regex
3. `_already_logged(path, vault_path)` — checks all vault folders for an
   existing card containing the file's slug
4. For new files: builds item dict with path, name, suffix, size, timestamp
5. `create_action_file(item)` — writes `FILE_*.md` with YAML frontmatter,
   infers priority, appends extension-specific action checklist

**Input:** Files in `watch_dir` not already in the vault

**Output:** `Vault/Inbox/FILE_YYYYMMDD_HHMMSS_<slug>.md` per new file

**Usage:**
```bash
# Standalone (single scan):
uv run python watchers/file_watcher.py

# With custom paths:
uv run python watchers/file_watcher.py /path/to/watch /path/to/vault
```

---

#### `gmail_watcher.py` — `watchers/gmail_watcher.py`

**Purpose:** Polls Gmail for unread priority emails and creates vault task
cards. Read-only OAuth2 — never sends, deletes, or modifies anything.

**How it works:**
1. `_get_service()` — load `token.json` → auto-refresh if expired → open
   browser only on first run → return authenticated Gmail API service
2. Build query: `is:unread (label:inbox OR label:important) (<keywords>)`
3. `messages.list()` — fetch message IDs matching the query
4. `messages.get(format="metadata")` — fetch From, Subject, snippet only
5. `create_action_file(item)` — writes `EMAIL_*.md` with Gmail message ID
   embedded in filename (deduplication key)

**Input:** Unread Gmail messages matching keyword filter

**Output:** `Vault/Inbox/EMAIL_YYYYMMDD_HHMMSS_<msgid>.md` per new email

**Usage:**
```bash
# Standalone (single check):
uv run python watchers/gmail_watcher.py

# With custom vault and interval:
uv run python watchers/gmail_watcher.py /path/to/vault 300
```

---

### 3.3 Python Helpers

#### `dashboard_updater.py` — `helpers/dashboard_updater.py`

**Purpose:** Single source of truth for all reads and writes to `Dashboard.md`.
No other module writes the dashboard directly.

**How it works:** Four public functions, each doing a targeted in-place edit:

```python
update_activity(vault_path, message)
    # Prepend timestamped entry to ## Recent Activity (cap at 20)

update_stats(vault_path, stat_name, value, operation='set')
    # Find stat row in ## Quick Stats table, set or increment value

update_component_status(vault_path, component, status, notes='')
    # Find component row in ## System Status table, rewrite with new status

refresh_vault_counts(vault_path)
    # Count .md files in Inbox/, Needs_Action/, Done/ → sync all task stats
```

Every write calls `_stamp()` to update the `_Last updated:` timestamp.

**Input:** `vault_path` + operation parameters

**Output:** Modified `Dashboard.md` in-place

**Usage:**
```bash
uv run python helpers/dashboard_updater.py --activity "2 new files detected"
uv run python helpers/dashboard_updater.py --stat files_monitored --value 2 --operation increment
uv run python helpers/dashboard_updater.py --component "File Monitor" --status running
uv run python helpers/dashboard_updater.py --refresh-counts
```

---

#### `inbox_processor.py` — `helpers/inbox_processor.py`

**Purpose:** Triage engine for the vault Inbox. Reads every card's frontmatter,
applies routing rules, and moves files to the correct destination folder.

**How it works:**
1. List all `.md` files in `Vault/Inbox/` (sorted alphabetically)
2. Parse YAML frontmatter via `python-frontmatter`
3. `_route(post, card_path)` → dispatches to `_route_file` or `_route_email`
4. `_move(src, dest_dir)` → `shutil.move()` with conflict resolution (`_1`, `_2` suffixes)
5. After all cards: `update_activity()` + `refresh_vault_counts()` + `update_component_status()`

**Input:** `.md` cards in `Vault/Inbox/`

**Output:** Cards moved to `Needs_Action/` or `Done/`; returns summary dict

```python
{
    "processed":       3,   # total cards handled
    "to_needs_action": 2,   # moved to Needs_Action/
    "to_done":         1,   # moved to Done/
    "errors":          []   # list of (filename, error_msg) tuples
}
```

**Usage:**
```bash
uv run python helpers/inbox_processor.py
uv run python helpers/inbox_processor.py --vault /path/to/vault
```

---

### 3.4 Main Orchestrator — `main.py`

**Purpose:** Runs `FileWatcher` and `GmailWatcher` continuously in separate
daemon threads. Monitors thread health, auto-restarts crashed watchers, and
shuts down cleanly on CTRL+C or SIGTERM.

**How it works:**

```
main.py
  └── Orchestrator
        ├── WatcherThread("FileWatcher")   → daemon thread
        │     └── FileWatcher.check_for_updates() + create_action_file()
        │           [loops every file_interval seconds]
        │
        ├── WatcherThread("GmailWatcher")  → daemon thread
        │     └── GmailWatcher.check_for_updates() + create_action_file()
        │           [loops every gmail_interval seconds]
        │
        └── _main_loop()                   → main thread
              ├── refresh_vault_counts()   every 60s
              └── _health_check()          every 300s
                    └── auto-restart any dead thread
```

**Input:**
```bash
python main.py [--vault-path PATH] [--file-interval INT] [--gmail-interval INT] [--log-level LEVEL]
```

**Output:** Continuous log to `logs/main.log` + console; vault cards + dashboard
updates from both watcher threads.

**Usage:**
```bash
# Start with defaults:
uv run python main.py

# Custom configuration:
uv run python main.py \
    --vault-path ~/AI_Employee_Vault \
    --file-interval 30 \
    --gmail-interval 120 \
    --log-level DEBUG
```

---

### 3.5 Vault Files

The vault (`AI_Employee_Vault/`) is the system's working memory. It is a
standard folder that can be opened as an Obsidian vault for linked note viewing.

---

#### `Dashboard.md`

Tracks live system state. Updated automatically after every watcher cycle.

| Section | What it tracks |
|---------|---------------|
| `## System Status` | ONLINE/OFFLINE/ERROR status per component with last-run timestamp |
| `## Quick Stats` | Cumulative counters: files monitored, emails checked, tasks in each folder |
| `## Recent Activity` | Last 20 timestamped events (auto-trimmed) |
| `_Last updated:_` | Timestamp of most recent write |

---

#### `Company_Handbook.md`

Defines the AI employee's operating rules and monitoring boundaries.

| Section | Content |
|---------|---------|
| Mission Statement | Privacy-respecting, non-intrusive operation principles |
| File Monitoring Rules | Watch `~/Downloads` only; log metadata only (never contents) |
| Gmail Monitoring Rules | Unread + keyword filter; subject + sender + snippet only |
| Task Workflow | `Inbox → Needs_Action → Done` — items never deleted |
| Available Skills | Table of all skills and their trigger conditions |
| Privacy & Security Rules | Explicit DO NOT list for monitoring and data storage |

---

#### `Inbox/` folder

**Purpose:** Landing zone for all newly detected items.

- File cards: `FILE_YYYYMMDD_HHMMSS_<slug>.md`
- Email cards: `EMAIL_YYYYMMDD_HHMMSS_<msgid>.md`
- All cards have `status: pending` frontmatter
- Cards remain here until `process-inbox` runs

---

#### `Needs_Action/` folder

**Purpose:** Holds items that require a human decision or follow-up action.

- Cards are moved here by `process-inbox` based on routing rules
- All emails always land here (no email is auto-discarded)
- All substantive file types land here (PDFs, docs, images, archives)
- Cards stay here until manually moved to `Done/`

---

#### `Done/` folder

**Purpose:** Permanent audit trail of resolved and auto-discarded items.

- Temp files (`.tmp`, `.temp`, `.bak`) are auto-discarded here
- Files named `test`, `temp`, or `delete` are auto-discarded here
- Human-resolved cards from `Needs_Action/` are moved here manually
- Items are **never deleted** — this folder is the system's history

---

## 4. Tools & Technologies

| Tool / Library | Version | Purpose | Usage in Project |
|----------------|---------|---------|-----------------|
| **Python** | 3.10+ | Programming language | All watchers, helpers, and `main.py` |
| **uv** | Latest | Fast Python package manager | Dependency installation and virtual env management |
| **Claude Code** | Latest | AI agent platform | Reads `.claude/skills/` and executes agent skill instructions |
| **Obsidian** | Latest | Markdown note-taking app | Visualises the vault as a linked notebook (optional) |
| **watchdog** | 6.0.0 | File system event library | Listed as dependency; current code uses `Path.iterdir()` for compatibility — available for Silver Tier live monitoring |
| **python-frontmatter** | 1.1.0 | YAML frontmatter parser | Parses task card metadata in `inbox_processor.py` |
| **google-api-python-client** | 2.193.0 | Official Google API client | Builds Gmail API service object in `gmail_watcher.py` |
| **google-auth-oauthlib** | 1.3.1 | OAuth 2.0 flow handler | Browser-based Gmail authorisation (`InstalledAppFlow`) |
| **google-auth-httplib2** | 0.3.1 | HTTP transport for Google auth | Token refresh via `Request()` in `gmail_watcher.py` |
| **Gmail API v1** | — | Google's email REST API | `messages.list` + `messages.get` (metadata only) |
| **Git** | Any | Version control | Source code management; `.gitignore` protects credentials |

---

## 5. Privacy & Security

### 5.1 What Gets Monitored

| Source | What is monitored | Frequency |
|--------|------------------|-----------|
| File system | `~/Downloads/file_check/` — new file names, sizes, extensions | Every 60 seconds (configurable) |
| Gmail | Unread emails in inbox/important matching keywords | Every 120 seconds (configurable) |

### 5.2 What NEVER Gets Monitored

**File system blacklist** — these patterns are permanently blocked via regex.
No vault card is ever created for a file matching any of these:

```
.ssh          SSH private keys
.config       Application credentials and settings
.env          Environment variable files (almost always contain secrets)
credentials   Any file with "credentials" in the path
passwords     Any file with "passwords" in the path
secret        Any file with "secret" in the path
private_key   Private key material
id_rsa        SSH private keys
.pem          Certificate and key files
.p12          PKCS#12 certificate bundles
.pfx          Personal Information Exchange files
```

Additionally skipped automatically:
- Files starting with `.` (hidden files)
- Files starting with `~` (temp/lock files)
- Files ending with `.tmp` or `.part` (incomplete downloads)

**Gmail:**
- Full email body is never fetched (only subject, sender, 200-char snippet)
- Spam and Promotions labels are not scanned
- Draft and Sent folders are not scanned
- Attachments are never accessed

### 5.3 Data Storage

| Data | Where stored | What's stored |
|------|-------------|--------------|
| File task cards | `AI_Employee_Vault/Inbox/` | Filename, size, extension, timestamp, suggested actions |
| Email task cards | `AI_Employee_Vault/Inbox/` | Sender, subject, 200-char snippet, timestamp |
| Dashboard | `AI_Employee_Vault/Dashboard.md` | Counters, status, activity log messages |
| Logs | `logs/main.log` | Timestamps, event descriptions, error messages |

- **No file contents** are ever read or stored
- **No email body** beyond 200-char snippet is ever stored
- **All data is local** — nothing leaves your machine
- **No database** — everything is plain Markdown files

### 5.4 API Permissions

| API | Scope | Can it do | Cannot do |
|-----|-------|-----------|-----------|
| Gmail API | `gmail.readonly` | List messages, read metadata/snippet | Send email, delete email, modify labels, access Drive |

**OAuth token security:**
- `credentials.json` — OAuth app identity from Google Cloud Console
- `token.json` — personal access token, auto-refreshed, never committed to git
- Both files are in `.credentials/` which is listed in `.gitignore`
- To fully revoke access: `myaccount.google.com/permissions` → remove "AI Employee"

---

## 6. Configuration

### 6.1 File Locations

| Resource | Default Path |
|----------|-------------|
| Vault | `~/AI_Employee_Vault/` |
| Project | `~/projects/ai-employee-project/` |
| Credentials | `.credentials/credentials.json` (relative to project) |
| Logs | `logs/main.log` (relative to project) |
| Watch folder | `~/Downloads/file_check/` |

### 6.2 Watcher Intervals

| Watcher | Default interval | CLI argument |
|---------|-----------------|-------------|
| File watcher | 60 seconds | `--file-interval` |
| Gmail watcher | 120 seconds | `--gmail-interval` |
| Dashboard refresh | 60 seconds (hardcoded in `_main_loop`) | — |
| Health check | 300 seconds (hardcoded) | — |

### 6.3 Configurable CLI Arguments

```bash
python main.py [OPTIONS]

  --vault-path PATH        Path to vault root
                           Default: ~/AI_Employee_Vault

  --file-interval INT      FileWatcher poll interval in seconds
                           Default: 60

  --gmail-interval INT     GmailWatcher poll interval in seconds
                           Default: 120

  --log-level LEVEL        DEBUG | INFO | WARNING | ERROR
                           Default: INFO
```

### 6.4 Environment Variables

None required. All configuration is via CLI arguments or code defaults.
The `.env` file pattern is explicitly blacklisted from monitoring and should
never be created in this project.

### 6.5 Skill Configuration

Each skill's `SKILL.md` frontmatter contains a `config:` block with
human-readable defaults. These are documentation/reference only — the actual
runtime values are in the Python files. To change a value, update both.

```yaml
# Example from file-monitor/SKILL.md:
config:
  monitored_folders:
    - ~/Downloads/file_check   # ← matches FileWatcher default in file_watcher.py
  ignored_patterns:
    - .ssh
    - .env
    # ...
```

---

## 7. How It Works — Complete Example

### Scenario: User downloads `invoice_April.pdf`

---

**Step 1 — Detection**

```
~/Downloads/file_check/invoice_April.pdf  ← file appears

main.py → WatcherThread("FileWatcher") → _run_loop()
  └── FileWatcher.check_for_updates()
        ├── Iterates ~/Downloads/file_check/
        ├── _is_safe("invoice_April.pdf")
        │     ├── starts with "."?  NO
        │     ├── starts with "~"?  NO
        │     ├── ends with .tmp?   NO
        │     └── matches blacklist? NO  ✓ SAFE
        ├── _already_logged("invoice_April.pdf", vault_path)
        │     ├── Check Inbox/         — no match
        │     ├── Check Needs_Action/  — no match
        │     └── Check Done/          — no match  ✓ NEW
        └── Returns: [{ path, name, suffix=".pdf", size_bytes, detected_at }]
```

---

**Step 2 — Task Creation**

```
FileWatcher.create_action_file(item)
  ├── vault_inbox = AI_Employee_Vault/Inbox/
  ├── ts_slug = "20260406_143022"
  ├── name_slug = "invoice_April_pdf"  (sanitised)
  ├── priority = _infer_priority("invoice_April.pdf", ".pdf")  → "high"
  ├── actions = _suggested_actions(".pdf")  → PDF review checklist
  └── Writes: FILE_20260406_143022_invoice_April_pdf.md

Contents of the created card:
┌─────────────────────────────────────────────────────────┐
│ ---                                                     │
│ type: file                                              │
│ file_name: "invoice_April.pdf"                          │
│ file_path: "/home/user/Downloads/file_check/invoice_Ap…"│
│ file_size: "245.3 KB"                                   │
│ file_type: ".pdf"                                       │
│ detected_at: "2026-04-06 14:30:22 UTC"                  │
│ priority: high                                          │
│ status: pending                                         │
│ ---                                                     │
│                                                         │
│ # New File: invoice_April.pdf                           │
│                                                         │
│ ## Suggested Actions                                    │
│ - [ ] Open and review PDF contents                      │
│ - [ ] Check sender/source legitimacy                    │
│ - [ ] File in appropriate project folder                │
│ - [ ] Extract key data if needed                        │
└─────────────────────────────────────────────────────────┘
```

---

**Step 3 — Dashboard Update**

```
WatcherThread._update_dashboard(vault_path, n=1)
  ├── update_activity(vault_path, "File Monitor: 1 new file(s) detected")
  │     └── Dashboard.md → ## Recent Activity
  │           + `- \`2026-04-06 14:30\` -- File Monitor: 1 new file(s) detected`
  │
  ├── update_component_status(vault_path, "File Monitor", "online")
  │     └── Dashboard.md → ## System Status → File Monitor row
  │           "ONLINE  | 2026-04-06 14:30 | OK"
  │
  ├── update_stats(vault_path, "files_monitored", 1, "increment")
  │     └── Dashboard.md → ## Quick Stats → Files monitored: 4 → 5
  │
  └── refresh_vault_counts(vault_path)
        └── Dashboard.md → Tasks in Inbox: 1, Needs_Action: 2, Done: 3
```

---

**Step 4 — User Review (in Obsidian or any editor)**

```
User opens ~/AI_Employee_Vault/ in Obsidian

Dashboard.md shows:
  ✓ File Monitor     ONLINE   14:30  OK
  ✓ Files monitored: 5
  ✓ Tasks in Inbox:  1
  ✓ Recent Activity: File Monitor: 1 new file(s) detected

User navigates to Inbox/
  → Sees: FILE_20260406_143022_invoice_April_pdf.md
  → Opens it, reads the suggested actions checklist
  → Decides this needs attention
```

---

**Step 5 — Triage (user says "process inbox")**

```
process_inbox(vault_path)
  ├── Reads: FILE_20260406_143022_invoice_April_pdf.md
  ├── Parses frontmatter: type=file, file_type=".pdf"
  ├── _route_file() → ".pdf" in DOCUMENT_EXTENSIONS → "needs_action"
  ├── _move(card, Needs_Action/)
  │     → AI_Employee_Vault/Needs_Action/FILE_20260406_143022_invoice_April_pdf.md
  └── refresh_vault_counts() → Tasks in Inbox: 0, Needs_Action: 3

User marks it done when invoice is processed
  → Manually moves card to Done/   (permanent audit record)
```

---

## 8. Error Handling

### 8.1 File Watcher Errors

| Error | Behaviour |
|-------|-----------|
| Watch directory does not exist | Logs warning, returns empty list, watcher continues |
| File stat fails (permission denied) | Logs warning, skips that file, continues with others |
| Vault Inbox create fails (disk full) | Exception bubbles to `WatcherThread`, logged, thread continues |
| File already logged (duplicate) | Silently skipped — added to `_seen_paths` in-memory set |

### 8.2 Gmail Watcher Errors

| Error | Behaviour |
|-------|-----------|
| `credentials.json` missing | `FileNotFoundError` raised at init → thread exits, health check will restart |
| Token expired with refresh token | `creds.refresh(Request())` called automatically — no user action needed |
| Token refresh fails (network error) | `TransportError` raised → thread exits → health check restarts within 300s |
| `credentials.json` corrupted | Warning logged, `creds = None`, re-auth flow triggered |
| Gmail API 429 (rate limit) | `HttpError` caught, logged, returns empty list, retries next interval |
| Gmail API 403 (auth revoked) | `HttpError` caught, logged — requires user to re-authorise manually |
| No matching emails | Returns `[]` — no cards created, no error |

### 8.3 Dashboard Updater Errors

| Error | Behaviour |
|-------|-----------|
| `Dashboard.md` missing | `FileNotFoundError` raised — caller logs warning, dashboard update skipped |
| Section header not found in dashboard | `ValueError` caught, warning printed, that operation skipped |
| Stat row not found in table | Warning printed, returns — dashboard unchanged |
| Component row not found | Warning printed, returns — dashboard unchanged |

### 8.4 Main Orchestrator Errors

| Error | Behaviour |
|-------|-----------|
| Watcher thread crashes | `WatcherThread._run_loop` catches the exception, logs it, thread exits |
| Thread found dead at health check | `_health_check()` calls `wt.start()` to restart the thread |
| CTRL+C (SIGINT) | `_handle_signal()` called → `orchestrator.shutdown()` → all threads stopped → `sys.exit(0)` |
| SIGTERM (Linux/macOS) | Same as SIGINT — graceful shutdown |

---

## 9. Limitations & Known Issues

### 9.1 Bronze Tier Limitations

| Limitation | Detail |
|-----------|--------|
| Manual triage required | `process-inbox` must be invoked by the user — it does not run automatically |
| Read-only Gmail | The system cannot send, reply to, or label any emails |
| Single watch folder | Only `~/Downloads/file_check/` is monitored by default (configurable) |
| No approval workflow | There is no HITL (human-in-the-loop) approval mechanism |
| No scheduling | The orchestrator must be started manually — no cron integration |
| No cloud deployment | Designed for local desktop use only |
| No third-party integrations | No Slack, WhatsApp, LinkedIn, Calendar, or accounting tools |

### 9.2 Known Issues

| Issue | Detail | Workaround |
|-------|--------|-----------|
| First Gmail auth requires browser | OAuth browser flow cannot run headlessly | Complete auth on a machine with a browser; `token.json` works everywhere after |
| File detection delay | Up to 60 seconds between file arrival and card creation (poll interval) | Reduce `--file-interval` to 10–30s for faster detection |
| Gmail API quota | 1 billion units/day (free tier) — effectively unlimited for this use case | N/A — quota will never be reached |
| `token.json` not portable | Tied to the authorising machine's Google session | Re-authorise on each new machine |
| Duplicate `_already_logged` exit | Dead code path in `gmail_watcher.py` line 244 | Cosmetic only — does not affect functionality |

---

## 10. Future Enhancements

### Silver Tier Additions

| Feature | Description |
|---------|-------------|
| Scheduled automation | Auto-run watchers on a cron schedule — no manual start needed |
| Google Calendar integration | Surface upcoming deadlines in the dashboard |
| Smart email summarisation | Claude reads snippets and writes plain-English summaries per card |
| Automatic inbox processing | `process-inbox` runs after every watcher cycle automatically |
| Priority scoring | Automatic 1–5 priority score on every task card |
| Multi-folder watching | Configurable watch list (not just Downloads) |
| WhatsApp monitoring | Read-only monitoring of WhatsApp messages via API |
| LinkedIn monitoring | Surface connection requests and priority messages |
| Weekly digest | Auto-generated weekly summary of all Done items |

### Gold Tier Additions

| Feature | Description |
|---------|-------------|
| Email sending with approval | Draft replies, present to human for one-click send |
| HITL approval workflow | Any outbound action requires explicit approval before execution |
| Odoo accounting integration | Auto-log invoices from email cards into accounting system |
| Facebook/Instagram monitoring | Surface brand mentions and DMs |
| Twitter/X integration | Monitor mentions, DMs, and trending topics |
| CEO weekly briefing | Auto-generated executive summary of all activity |
| Autonomous loop mode | Continuous self-directed operation within defined guardrails |
| Comprehensive audit logging | Tamper-evident log of every action taken by the AI employee |

---

## 11. Troubleshooting

**Issue: File watcher not detecting files**
```
Diagnosis: Check main.py is running and the watch folder exists.

1. Verify the orchestrator is running:
   ps aux | grep main.py       # Mac/Linux
   tasklist | findstr python   # Windows

2. Confirm the watch folder path:
   ls ~/Downloads/file_check/

3. Check the logs:
   tail -50 logs/main.log

4. Drop a test file and watch for a card within 60 seconds:
   echo "test" > ~/Downloads/file_check/test.txt
```

---

**Issue: Gmail watcher authorisation failed**
```
Diagnosis: Google account not added as test user, or token revoked.

1. Go to Google Cloud Console → APIs & Services → OAuth consent screen
2. Edit app → Test users → add your Gmail address → Save
3. Delete the old token:
   rm .credentials/token.json
4. Run the watcher — browser auth flow will repeat once:
   uv run python watchers/gmail_watcher.py
```

---

**Issue: Dashboard not updating**
```
Diagnosis: Vault path mismatch or Dashboard.md missing.

1. Confirm Dashboard.md exists:
   ls ~/AI_Employee_Vault/Dashboard.md

2. Run a manual dashboard update to test:
   uv run python helpers/dashboard_updater.py \
       --vault ~/AI_Employee_Vault \
       --refresh-counts

3. Check the vault path matches what main.py was started with:
   grep "vault" logs/main.log | head -5
```

---

**Issue: Task cards not appearing in Obsidian**
```
Diagnosis: Obsidian cache or wrong vault opened.

1. Press CTRL+R in Obsidian to force a vault refresh
2. Confirm you opened the correct folder (the vault, not the project):
   Correct:   ~/AI_Employee_Vault/
   Incorrect: ~/projects/ai-employee-project/
3. Check the file exists on disk:
   ls ~/AI_Employee_Vault/Inbox/
```

---

**Issue: `ModuleNotFoundError: No module named 'frontmatter'`**
```
Diagnosis: Wrong Python interpreter — not using the uv environment.

Always use:  uv run python <script>
Not:         python <script>

Reinstall if needed:
   uv pip install python-frontmatter
```

---

**Issue: `This app isn't verified` warning in browser**
```
Diagnosis: Expected behaviour for personal/test OAuth apps.

Click: Advanced → Go to AI Employee (unsafe) → grant permission.
This warning appears because the app has not been submitted to Google
for verification. For personal use, this is safe to proceed through.
```

---

## 12. References

| Resource | URL |
|----------|-----|
| Claude Code Documentation | https://docs.claude.ai/claude-code |
| Obsidian Documentation | https://help.obsidian.md |
| Gmail API Documentation | https://developers.google.com/gmail/api |
| Gmail API Reference (messages) | https://developers.google.com/gmail/api/reference/rest/v1/users.messages |
| Google OAuth 2.0 Guide | https://developers.google.com/identity/protocols/oauth2 |
| Watchdog Documentation | https://python-watchdog.readthedocs.io |
| python-frontmatter | https://python-frontmatter.readthedocs.io |
| uv Package Manager | https://docs.astral.sh/uv |
| Google Cloud Console | https://console.cloud.google.com |
| Gmail API Quota Info | https://developers.google.com/gmail/api/reference/quota |

---

<div align="center">

**AI Employee — Bronze Tier**

*Built for the AI Employee Hackathon*

[Code Documentation](documents/CODE_DOCUMENTATION.md) · [Deployment Guide](documents/DEPLOYMENT_GUIDE.md) · [Gmail Setup](documents/GMAIL_SETUP.md)

</div>
