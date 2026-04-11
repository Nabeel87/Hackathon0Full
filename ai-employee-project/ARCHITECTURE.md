# AI Employee — System Architecture

**Tier:** Silver v2.0.0  
**Last updated:** 2026-04-11

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Layer Overview](#2-layer-overview)
3. [Orchestrator](#3-orchestrator)
4. [Watcher Architecture](#4-watcher-architecture)
5. [Agent Skills Architecture](#5-agent-skills-architecture)
6. [HITL Approval Workflow](#6-hitl-approval-workflow)
7. [MCP Server Architecture](#7-mcp-server-architecture)
8. [Scheduling System](#8-scheduling-system)
9. [Priority Routing Logic](#9-priority-routing-logic)
10. [Vault Structure](#10-vault-structure)
11. [Session Management](#11-session-management)
12. [Data Flow — End to End](#12-data-flow--end-to-end)
13. [Component Inventory](#13-component-inventory)

---

## 1. Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Skills are instructions, not code** | Every `.claude/skills/*/SKILL.md` is pure Markdown — no logic, no Python, no regex |
| **Python is the engine** | All computation lives in `watchers/`, `helpers/`, `mcp_servers/`, `scheduler/` |
| **Human gates all outbound actions** | No email or post executes without explicit approval — enforced by `Pending_Approval/` workflow |
| **Read-only monitoring** | Watchers never write to external sources; they only create local vault cards |
| **Local-only storage** | All data is Markdown files on disk — no cloud services, no databases |
| **Privacy by design** | Content never logged, only previews; sensitive filenames blacklisted |
| **Graceful degradation** | Each watcher thread fails independently; others continue unaffected |

---

## 2. Layer Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CLAUDE CODE (user interface)                                            │
│  User speaks natural language → Claude reads SKILL.md → calls Python    │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────┐
│  AGENT SKILLS LAYER  (.claude/skills/)                                   │
│  12 pure-Markdown skill files — each defines:                            │
│    • Trigger phrases  • Process steps  • Python module to call           │
│    • Expected output  • Error handling  • Dependencies                   │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │  plain-English → Python calls
┌──────────────────────────────────────▼──────────────────────────────────┐
│  PYTHON LAYER                                                            │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  main.py  (Orchestrator)                                         │   │
│  │  • 4 WatcherThread daemons (auto-restart on crash)               │   │
│  │  • BackgroundScheduler (4 APScheduler jobs)                      │   │
│  │  • Health check every 5 min  •  Dashboard refresh every 60s      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  watchers/          helpers/            mcp_servers/    scheduler/       │
│  file_watcher       dashboard_updater   email_server    scheduled_tasks  │
│  gmail_watcher      inbox_processor     (Gmail send)    check_approvals  │
│  linkedin_watcher   linkedin_poster                                      │
│  whatsapp_watcher   plan_creator                                         │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │  read/write Markdown files
┌──────────────────────────────────────▼──────────────────────────────────┐
│  VAULT LAYER  (AI_Employee_Vault/)                                       │
│  Inbox/  Needs_Action/  Done/  Plans/  Pending_Approval/  Approved/      │
│  Rejected/  Dashboard.md  Company_Handbook.md                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Orchestrator

`main.py` is the single entry point for continuous operation.

```
  Orchestrator.__init__()
  ├── WatcherThread("FileWatcher",     FileWatcher,     interval=60s)
  ├── WatcherThread("GmailWatcher",    GmailWatcher,    interval=120s)
  ├── WatcherThread("LinkedInWatcher", LinkedInWatcher, interval=180s)
  └── WatcherThread("WhatsAppWatcher", WhatsAppWatcher, interval=60s)

  Orchestrator.start()
  ├── start all 4 WatcherThreads (daemon=True)
  ├── build BackgroundScheduler from scheduled_tasks registry
  ├── scheduler.start()
  └── _main_loop()
        ├── every 60s  → _refresh_dashboard()
        ├── every 300s → _health_check()  (restart dead threads)
        └── SIGINT/SIGTERM → shutdown() → stop all threads + scheduler

  WatcherThread._run_loop()  (runs in its own thread)
  ├── instantiate watcher class
  ├── loop:
  │     ├── check_for_updates() → list[dict]
  │     ├── for each item: create_action_file(item) → Path
  │     ├── if cards created: _update_dashboard()
  │     └── sleep check_interval seconds (1s ticks, interruptible)
  └── on crash: health check auto-restarts after RESTART_DELAY (10s)
```

**Thread isolation:** each watcher crashes independently — a Playwright
timeout in `WhatsAppWatcher` does not affect `GmailWatcher`.

---

## 4. Watcher Architecture

All watchers inherit from `BaseWatcher` (abstract base class):

```
  BaseWatcher (ABC)
  ├── vault_path : Path
  ├── check_interval : int
  ├── logger : Logger
  ├── _running : bool
  │
  ├── check_for_updates() → list[dict]   [abstract]
  ├── create_action_file(item) → Path    [abstract]
  ├── post_cycle(n)                      [optional override]
  ├── run()                              [main polling loop]
  ├── stop()                             [signal loop to exit]
  └── _interruptible_sleep(seconds)

  ┌────────────────┬──────────────────────────────────────────────────┐
  │ Watcher        │ Mechanism                                         │
  ├────────────────┼──────────────────────────────────────────────────┤
  │ FileWatcher    │ os.scandir() — no external dependencies           │
  │ GmailWatcher   │ Gmail REST API via google-api-python-client       │
  │ LinkedInWatcher│ Playwright Chromium (headless after first login)  │
  │ WhatsAppWatcher│ Playwright Chromium (headless after QR login)     │
  └────────────────┴──────────────────────────────────────────────────┘
```

**Deduplication:** every watcher maintains a `_seen_ids: set[str]` in
memory and checks vault folders (`Inbox/`, `Needs_Action/`, `Done/`) on
disk before creating a card — prevents duplicate cards across restarts.

---

## 5. Agent Skills Architecture

```
  .claude/skills/
  │
  ├── MONITORING SKILLS (read-only, no approval needed)
  │   ├── file-monitor/SKILL.md       → FileWatcher.check_for_updates()
  │   ├── gmail-monitor/SKILL.md      → GmailWatcher.check_for_updates()
  │   ├── linkedin-monitor/SKILL.md   → LinkedInWatcher.check_for_updates()
  │   └── whatsapp-monitor/SKILL.md   → WhatsAppWatcher.check_for_updates()
  │
  ├── ACTION SKILLS (write to Pending_Approval/, require HITL)
  │   ├── send-email/SKILL.md         → email_server.draft_email()
  │   └── post-linkedin/SKILL.md      → linkedin_poster.post_to_linkedin()
  │
  ├── APPROVAL SKILLS (execute or cancel pending actions)
  │   ├── approve-action/SKILL.md     → reads Pending_Approval/, executes, → Done/
  │   └── reject-action/SKILL.md      → reads Pending_Approval/, archives → Rejected/
  │
  ├── UTILITY SKILLS (vault management)
  │   ├── create-plan/SKILL.md        → plan_creator.create_plan()
  │   ├── process-inbox/SKILL.md      → inbox_processor.process_inbox()
  │   ├── update-dashboard/SKILL.md   → dashboard_updater.*()
  │   └── skill-creator/SKILL.md      → creates new SKILL.md from template
  │
  └── META SKILL
      └── skill-creator/SKILL.md      → self-referential; creates other skills

  Skill file contract (enforced by skill-creator checklist):
  ┌────────────────────────────────────────────────────────────────┐
  │  MUST HAVE:  name, description, triggers (≥2), config block    │
  │  MUST HAVE:  Purpose, Process, How to Run, Output, Expected    │
  │              Output, Dependencies, Notes sections              │
  │  MUST NOT:   contain Python code blocks                        │
  │  MUST:       reference an actual file in watchers/ or helpers/ │
  └────────────────────────────────────────────────────────────────┘
```

---

## 6. HITL Approval Workflow

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                   HITL APPROVAL WORKFLOW                        │
  └─────────────────────────────────────────────────────────────────┘

  User: "send email to alice@example.com re: invoice"
       │
       ▼
  send-email skill reads SKILL.md
       │
       ▼
  email_server.draft_email() called
       │
       ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Vault/Pending_Approval/EMAIL_DRAFT_20260411_143022_xxx.md   │
  │  ---                                                         │
  │  action_type: send_email                                     │
  │  status: pending                                             │
  │  created: 2026-04-11T14:30:22                                │
  │  expires: 2026-04-12T14:30:22   ← 24-hour window            │
  │  to: "alice@example.com"                                     │
  │  subject: "Invoice #1234"                                    │
  │  ---                                                         │
  └──────────────────────────────────────────────────────────────┘
       │
       ├──── Human says: "approve the email"
       │          │
       │          ▼
       │     approve-action skill
       │          │
       │          ▼
       │     email_server.send_email() → Gmail API → sent
       │          │
       │          ▼
       │     card moved to Approved/ → Done/
       │
       ├──── Human says: "reject the email"
       │          │
       │          ▼
       │     reject-action skill
       │          │
       │          ▼
       │     card moved to Rejected/ (with reason logged)
       │
       └──── 24 hours pass with no decision
                  │
                  ▼
             check_approvals.py (runs hourly via APScheduler)
                  │
                  ▼
             expires < now → status: auto_rejected → Rejected/
                  │
                  ▼
             Dashboard activity log updated
```

**Card lifecycle states:**

```
  pending  →  approved  →  executed  →  (in Done/)
  pending  →  rejected              →  (in Rejected/)
  pending  →  auto_rejected         →  (in Rejected/)
```

---

## 7. MCP Server Architecture

```
  ┌──────────────────────────────────────────────────────────────┐
  │              EMAIL MCP SERVER  (mcp_servers/email_server.py) │
  └──────────────────────────────────────────────────────────────┘

  Public interface:
  ┌─────────────────────┬────────────────────────────────────────┐
  │ Function            │ Purpose                                │
  ├─────────────────────┼────────────────────────────────────────┤
  │ draft_email()       │ Create Pending_Approval card; no send  │
  │ send_email()        │ Send via Gmail API (post-approval only)│
  │ test_send_email()   │ Integration smoke test                 │
  │ _validate_recipients│ Reject malformed email addresses       │
  └─────────────────────┴────────────────────────────────────────┘

  Gmail OAuth2 flow:
  ┌──────────────────────────────────────────────────────────────┐
  │  .credentials/credentials.json  ← downloaded from Google    │
  │            │                                                  │
  │            ▼                                                  │
  │  InstalledAppFlow.run_local_server()  (first run only)       │
  │            │                                                  │
  │            ▼                                                  │
  │  .credentials/token.json  ← auto-created, auto-refreshed    │
  │            │                                                  │
  │            ▼                                                  │
  │  build("gmail", "v1", credentials=creds)                     │
  │            │                                                  │
  │    Scopes: gmail.readonly  (GmailWatcher)                    │
  │            gmail.send      (email_server)                    │
  └──────────────────────────────────────────────────────────────┘

  Security contract:
  • draft_email() NEVER calls the Gmail API — it only writes a local file
  • send_email() is ONLY called by approve-action skill after HITL approval
  • Recipient validation runs before any API call
  • Email body content is never written to logs (privacy)
```

---

## 8. Scheduling System

```
  ┌──────────────────────────────────────────────────────────────┐
  │         APSCHEDULER  (BackgroundScheduler)                   │
  │         Registered via scheduler/scheduled_tasks.py          │
  └──────────────────────────────────────────────────────────────┘

  Task registry (get_scheduled_tasks() → list[dict]):

  ┌─────────────────────────────┬──────────────────┬────────────────────────┐
  │ Task                        │ Trigger           │ Function               │
  ├─────────────────────────────┼──────────────────┼────────────────────────┤
  │ Approval Timeout Check      │ IntervalTrigger   │ check_approval_timeouts│
  │                             │ every 1 hour      │ → auto-reject expired  │
  ├─────────────────────────────┼──────────────────┼────────────────────────┤
  │ Generate Daily Summary      │ CronTrigger       │ generate_daily_summary │
  │                             │ hour=18, min=0    │ → DAILY_SUMMARY_*.md   │
  ├─────────────────────────────┼──────────────────┼────────────────────────┤
  │ Cleanup Old Files           │ CronTrigger       │ cleanup_old_files      │
  │                             │ day_of_week=sun   │ → archive Done/ ≥90d   │
  │                             │ hour=0, min=0     │                        │
  ├─────────────────────────────┼──────────────────┼────────────────────────┤
  │ Health Check                │ IntervalTrigger   │ run_health_check       │
  │                             │ every 30 min      │ → log component status │
  └─────────────────────────────┴──────────────────┴────────────────────────┘

  Job defaults:
    coalesce        = True   # missed jobs collapse into one
    max_instances   = 1      # never run a task twice in parallel
    misfire_grace   = 60s    # tolerate up to 60s late start

  Scheduler lifecycle (in Orchestrator):
    _build_scheduler()  → register all jobs → return sched (not started)
    sched.start()       → starts background thread
    health_check        → restarts if sched.running is False
    shutdown()          → sched.shutdown(wait=False)
```

---

## 9. Priority Routing Logic

```
  ┌──────────────────────────────────────────────────────────────┐
  │               PRIORITY ROUTING FLOWCHART                     │
  └──────────────────────────────────────────────────────────────┘

  Watcher detects item (file, email, message)
          │
          ▼
  Extract content metadata
  (subject / text / filename — preview only)
          │
          ▼
  ┌───────────────────────────────────────────┐
  │  Keyword scan (case-insensitive)           │
  │                                            │
  │  HIGH:   urgent, asap, emergency,          │
  │          critical, deadline, important,    │
  │          client, payment                   │
  │                                            │
  │  NORMAL: invoice, meeting (+ any file)     │
  └───────────────────────────────────────────┘
          │
    ┌─────┴──────┐
    │            │
  HIGH        NORMAL
    │            │
    ▼            ▼
priority: high   priority: normal
    │            │
    ▼            ▼
Needs_Action/  Inbox/
(review now)  (review later)

  Vault card frontmatter:
    priority: high    →  Needs_Action/ (direct routing in process-inbox)
    priority: normal  →  Inbox/       (default landing zone)

  process-inbox routing table:
    .pdf, .docx, .xlsx  →  Needs_Action/  (business documents)
    .mp3, .mp4, .jpg    →  Done/          (media, auto-close)
    .tmp, .log, .cache  →  Done/          (temp files, discard)
    priority: high      →  Needs_Action/  (regardless of type)
    everything else     →  Needs_Action/  (default: review)
```

---

## 10. Vault Structure

```
  AI_Employee_Vault/
  │
  ├── Dashboard.md              ← live system status (auto-updated every 60s)
  │
  ├── Company_Handbook.md       ← monitoring rules + privacy policy
  │
  ├── Inbox/                    ← all new cards land here first
  │   ├── FILE_*.md             ← from FileWatcher
  │   ├── EMAIL_*.md            ← from GmailWatcher
  │   ├── LINKEDIN_*.md         ← from LinkedInWatcher
  │   └── WHATSAPP_*.md         ← from WhatsAppWatcher
  │
  ├── Needs_Action/             ← high-priority items awaiting human action
  │   └── (cards moved from Inbox by process-inbox)
  │
  ├── Done/                     ← resolved, discarded, or auto-closed
  │   └── (cards moved from Needs_Action; cleaned up weekly)
  │
  ├── Plans/                    ← structured plans for complex tasks
  │   └── PLAN_YYYYMMDD_*.md    ← created by create-plan skill
  │
  ├── Pending_Approval/         ← awaiting human decision (24h window)
  │   ├── EMAIL_DRAFT_*.md      ← from send-email skill
  │   └── LINKEDIN_POST_*.md    ← from post-linkedin skill
  │
  ├── Approved/                 ← approved actions (transitional; moves to Done/)
  │
  ├── Rejected/                 ← rejected actions with reason logged
  │
  └── history/
      └── DAILY_SUMMARY_*.md    ← daily activity reports from scheduler
```

**Card filename conventions:**

| Type | Filename pattern |
|------|-----------------|
| File | `FILE_YYYYMMDD_HHMMSS_<slug>.md` |
| Email | `EMAIL_YYYYMMDD_HHMMSS_<msgid>.md` |
| LinkedIn | `LINKEDIN_YYYYMMDD_HHMMSS_<slug>.md` |
| WhatsApp | `WHATSAPP_YYYYMMDD_HHMMSS_<contact_slug>.md` |
| Email draft | `EMAIL_DRAFT_YYYYMMDD_HHMMSS_<id>.md` |
| LinkedIn post | `LINKEDIN_POST_YYYYMMDD_HHMMSS_<id>.md` |
| Plan | `PLAN_YYYYMMDD_HHMMSS_<title_slug>.md` |
| Daily summary | `DAILY_SUMMARY_YYYYMMDD.md` |

---

## 11. Session Management

Both browser-based watchers use Playwright persistent storage states:

```
  ~/.credentials/
  ├── credentials.json          ← Gmail OAuth client secrets (from Google Cloud)
  ├── token.json                ← Gmail OAuth token (auto-created, auto-refreshed)
  ├── linkedin_session/
  │   └── context.json          ← Playwright storage state (cookies + localStorage)
  └── whatsapp_session/
      └── context.json          ← Playwright storage state (cookies + localStorage)

  First-run flow (both LinkedIn and WhatsApp):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  1. Launch Chromium in headed mode (visible browser window)          │
  │  2. Navigate to LinkedIn.com or web.whatsapp.com                     │
  │  3. User logs in manually (username/password or QR scan)             │
  │  4. Wait for authenticated page to load (chat list / feed)           │
  │  5. context.storage_state(path="context.json") → save to disk        │
  │  6. Close browser                                                     │
  └──────────────────────────────────────────────────────────────────────┘

  Subsequent runs:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  1. browser.new_context(storage_state="context.json") → load session │
  │  2. Navigate in headless mode (no visible window)                     │
  │  3. If session expired → log error → require manual re-login          │
  └──────────────────────────────────────────────────────────────────────┘

  Security:
  • context.json files are in ~/.credentials/ (outside project root)
  • Both paths are listed in .gitignore
  • No passwords or tokens stored in plain text in project files
```

---

## 12. Data Flow — End to End

### Scenario: WhatsApp urgent message → vault card

```
  1. WhatsAppWatcher._check_unread_messages()
     └── Playwright opens web.whatsapp.com (headless, saved session)
     └── Finds chat list items with unread badge
     └── _extract_message_data() → {contact, text, received_dt, phone}

  2. check_for_updates() filters by keywords
     └── "urgent client invoice ASAP" → contains 'urgent', 'client', 'payment'
     └── Not in _seen_ids → not already logged → include

  3. create_action_file(item)
     └── detect_priority() → "high"
     └── Write Vault/Inbox/WHATSAPP_20260411_143000_john_doe.md
     └── Add msg_id to _seen_ids

  4. WatcherThread._update_dashboard()
     └── update_activity() → "WhatsApp Monitor: 1 new message(s) detected"
     └── update_component_status() → "WhatsApp Monitor: online"
     └── update_stats() → whatsapp_messages_checked += 1
     └── refresh_vault_counts() → Inbox count updated in Dashboard.md

  5. process-inbox skill (user triggers or scheduler)
     └── inbox_processor reads WHATSAPP_20260411_143000_john_doe.md
     └── priority: high → move to Needs_Action/
     └── Dashboard.md → Needs_Action count updated
```

### Scenario: User requests send email → approval → sent

```
  1. User: "send email to alice@example.com about invoice"
     └── send-email SKILL.md read by Claude Code

  2. email_server.draft_email(to, subject, body, vault_path)
     └── _validate_recipients() checks address format
     └── Write Vault/Pending_Approval/EMAIL_DRAFT_*.md
     └── expires = now + 24h written to frontmatter

  3. User: "approve the email"
     └── approve-action SKILL.md read by Claude Code
     └── Find latest pending card in Pending_Approval/
     └── email_server.send_email() → Gmail API → message sent
     └── Card moved to Approved/ → Done/
     └── Dashboard activity updated

  4. (alternative) 24h passes with no decision
     └── check_approval_timeouts() runs (hourly APScheduler job)
     └── expires < now → status: auto_rejected
     └── Card moved to Rejected/
     └── Dashboard activity updated
```

---

## 13. Component Inventory

### Python Modules (11)

| File | Lines | Role |
|------|-------|------|
| `main.py` | 615 | Orchestrator, 4 WatcherThreads, APScheduler |
| `watchers/base_watcher.py` | 102 | Abstract base — polling loop contract |
| `watchers/file_watcher.py` | 249 | File system monitor |
| `watchers/gmail_watcher.py` | 313 | Gmail API monitor |
| `watchers/linkedin_watcher.py` | 609 | LinkedIn Playwright monitor |
| `watchers/whatsapp_watcher.py` | 430 | WhatsApp Playwright monitor |
| `helpers/dashboard_updater.py` | 369 | Dashboard read/write engine |
| `helpers/inbox_processor.py` | 254 | Inbox triage and routing |
| `helpers/linkedin_poster.py` | 442 | LinkedIn post automation |
| `helpers/plan_creator.py` | 743 | Plan.md generation |
| `mcp_servers/email_server.py` | 537 | Gmail send MCP server |
| `scheduler/scheduled_tasks.py` | 720 | APScheduler task registry |

### Agent Skills (12)

| Skill | Type | Trigger example |
|-------|------|----------------|
| `file-monitor` | Monitor | "check for new files" |
| `gmail-monitor` | Monitor | "check my email" |
| `linkedin-monitor` | Monitor | "check linkedin" |
| `whatsapp-monitor` | Monitor | "check whatsapp" |
| `send-email` | Action (HITL) | "send email to..." |
| `post-linkedin` | Action (HITL) | "post to linkedin" |
| `approve-action` | Approval | "approve the email" |
| `reject-action` | Approval | "reject the post" |
| `create-plan` | Utility | "create a plan for..." |
| `process-inbox` | Utility | "process inbox" |
| `update-dashboard` | Utility | "update dashboard" |
| `skill-creator` | Meta | "create skill [name]" |

### Test Suite (48 tests)

| File | Tests | What is covered |
|------|-------|----------------|
| `tests/test_whatsapp.py` | 8 | Watcher class, skill, session, priority, task file, main integration |
| `tests/test_linkedin.py` | 8 | Watcher class, session, poster, skill, approval workflow, main integration |
| `tests/test_email.py` | 8 | Server functions, skill, scopes, draft creation, folder structure, validation |
| `tests/test_plan.py` | 8 | Plan creator, skill file, vault output, frontmatter validation |
| `tests/test_approval.py` | 8 | Approval workflow, timeout, folder structure, audit trail |
| `tests/test_scheduler.py` | 8 | Task registration, trigger types, cron expressions |

---

*AI Employee — Silver Tier Architecture Document — v2.0.0*
