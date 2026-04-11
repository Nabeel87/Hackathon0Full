# AI Employee

![Silver Tier](https://img.shields.io/badge/Tier-Silver%20Complete-C0C0C0?style=for-the-badge&logo=checkmarx&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-6B46C1?style=for-the-badge&logo=anthropic&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-48%2F48%20Passing-22C55E?style=for-the-badge)

> An autonomous, privacy-respecting AI employee that monitors files, email,
> LinkedIn, and WhatsApp — creates structured task cards, gates every outbound
> action behind a human approval step, and runs entirely on your local machine.

---

## What It Does

| Capability | Detail |
|-----------|--------|
| **File monitoring** | Watches `~/Downloads/file_check` — creates a task card for every new file |
| **Gmail monitoring** | Scans Gmail (read-only) for unread priority emails matching business keywords |
| **LinkedIn monitoring** | Watches messages, connection requests, and notifications via Playwright |
| **WhatsApp monitoring** | Scans WhatsApp Web for unread messages containing business keywords |
| **Email sending** | Drafts emails for human approval before any Gmail send is executed |
| **LinkedIn posting** | Drafts posts for human review — never publishes without approval |
| **Plan creation** | Breaks complex tasks into structured `Plan.md` files with action steps |
| **HITL approval** | Every sensitive action goes `Pending_Approval → Approve/Reject → Execute` |
| **Scheduled automation** | APScheduler runs approval timeouts, daily summaries, and weekly cleanup |
| **Agent Skills** | Natural-language trigger phrases via Claude Code — no commands to memorise |

---

## Architecture

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                     AGENT SKILLS LAYER  (.claude/skills/)               │
  │  file-monitor  gmail-monitor  linkedin-monitor  whatsapp-monitor        │
  │  send-email    post-linkedin  create-plan        approve-action          │
  │  reject-action process-inbox  update-dashboard   skill-creator          │
  └──────────────────────────────────┬──────────────────────────────────────┘
                                     │  plain-English instructions
  ┌──────────────────────────────────▼──────────────────────────────────────┐
  │                     PYTHON LAYER  (watchers/ + helpers/ + main.py)      │
  │                                                                         │
  │  WATCHERS (parallel daemon threads)                                     │
  │  ┌──────────────┐ ┌──────────────┐ ┌────────────────┐ ┌─────────────┐  │
  │  │ file_watcher │ │gmail_watcher │ │linkedin_watcher│ │whatsapp_    │  │
  │  │    (60s)     │ │   (120s)     │ │    (180s)      │ │watcher (60s)│  │
  │  └──────┬───────┘ └──────┬───────┘ └───────┬────────┘ └──────┬──────┘  │
  │         └────────────────┴─────────────────┴─────────────────┘         │
  │                                   │  create task cards                  │
  │  HELPERS                          ▼                                     │
  │  ┌─────────────────────┐  ┌───────────────────┐  ┌──────────────────┐  │
  │  │  dashboard_updater  │  │  inbox_processor  │  │  linkedin_poster │  │
  │  │  (reads/writes .md) │  │  (routing engine) │  │  plan_creator    │  │
  │  └─────────────────────┘  └───────────────────┘  └──────────────────┘  │
  │                                                                         │
  │  MCP SERVER           SCHEDULER (APScheduler)                           │
  │  ┌─────────────────┐  ┌────────────────────────────────────────────┐   │
  │  │  email_server   │  │  approval timeout (1h)  daily summary (6PM)│   │
  │  │  (Gmail send)   │  │  file cleanup (weekly)  health check (30m) │   │
  │  └─────────────────┘  └────────────────────────────────────────────┘   │
  └──────────────────────────────────┬──────────────────────────────────────┘
                                     │  read/write Markdown
  ┌──────────────────────────────────▼──────────────────────────────────────┐
  │                     VAULT  (AI_Employee_Vault/)                          │
  │                                                                         │
  │  ┌──────────┐  ┌──────────────┐  ┌─────────┐  ┌───────┐               │
  │  │  Inbox/  │→ │Needs_Action/ │→ │  Done/  │  │Plans/ │               │
  │  └──────────┘  └──────────────┘  └─────────┘  └───────┘               │
  │                                                                         │
  │  ┌──────────────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
  │  │ Pending_Approval/│→ │ Approved/ │  │Rejected/ │  │ Dashboard.md │  │
  │  └──────────────────┘  └───────────┘  └──────────┘  └──────────────┘  │
  └─────────────────────────────────────────────────────────────────────────┘
```

---

## HITL Approval Workflow

All outbound actions (emails, LinkedIn posts) require human sign-off:

```
  Skill triggered
       │
       ▼
  Draft created → Vault/Pending_Approval/ACTION_*.md
       │
       ├──  Human approves  →  move to Approved/  →  execute  →  Done/
       │
       ├──  Human rejects   →  move to Rejected/  →  log reason
       │
       └──  24h timeout     →  auto-reject (scheduled task)
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Claude Code](https://claude.ai/code)
- Playwright Chromium (for LinkedIn + WhatsApp monitoring)

### 1 — Clone and install

```bash
git clone <repo-url> ai-employee-project
cd ai-employee-project
uv pip install -r requirements.txt
playwright install chromium
```

### 2 — Create the vault

```bash
mkdir -p ~/AI_Employee_Vault/{Inbox,Needs_Action,Done,Plans,Pending_Approval,Approved,Rejected}
mkdir -p ~/Downloads/file_check
```

### 3 — Gmail setup *(required for email monitoring and sending)*

Full walkthrough: [`documents/GMAIL_SETUP.md`](documents/GMAIL_SETUP.md)

Short version: Google Cloud Console → create project → enable Gmail API →
create OAuth Desktop credentials → save `credentials.json` to `.credentials/`.

### 4 — WhatsApp first-time login *(optional)*

```bash
python watchers/whatsapp_watcher.py
# Browser opens — scan the QR code with your phone.
# Session is saved; all future runs are headless.
```

### 5 — Start the orchestrator

```bash
uv run python main.py --vault-path ~/AI_Employee_Vault
```

### 6 — Open Claude Code and talk to it

```bash
cd ai-employee-project
claude
```

```
"check for new files"      →  FILE_*.md cards in Inbox/
"check my email"           →  EMAIL_*.md cards in Inbox/
"check linkedin"           →  LINKEDIN_*.md cards in Inbox/
"check whatsapp"           →  WHATSAPP_*.md cards in Inbox/
"send email to alice@..."  →  draft → Pending_Approval/ → you approve → sent
"post to linkedin"         →  draft → Pending_Approval/ → you approve → posted
"process inbox"            →  routes all cards to Needs_Action/ or Done/
"update dashboard"         →  refreshes Dashboard.md stats
```

---

## Folder Structure

```
ai-employee-project/
├── .claude/skills/              # Agent Skills — plain Markdown instructions
│   ├── file-monitor/            # Trigger: "check for new files"
│   ├── gmail-monitor/           # Trigger: "check my email"
│   ├── linkedin-monitor/        # Trigger: "check linkedin"
│   ├── whatsapp-monitor/        # Trigger: "check whatsapp"
│   ├── send-email/              # Trigger: "send email to..."
│   ├── post-linkedin/           # Trigger: "post to linkedin"
│   ├── create-plan/             # Trigger: "create a plan for..."
│   ├── approve-action/          # Trigger: "approve [action]"
│   ├── reject-action/           # Trigger: "reject [action]"
│   ├── process-inbox/           # Trigger: "process inbox"
│   ├── update-dashboard/        # Trigger: "update dashboard"
│   └── skill-creator/           # Meta-skill: generates new skills
│
├── watchers/
│   ├── base_watcher.py          # Abstract base — shared polling loop
│   ├── file_watcher.py          # Filesystem scanner + card writer
│   ├── gmail_watcher.py         # Gmail API client + OAuth flow
│   ├── linkedin_watcher.py      # Playwright-based LinkedIn monitor
│   └── whatsapp_watcher.py      # Playwright-based WhatsApp monitor
│
├── helpers/
│   ├── dashboard_updater.py     # All Dashboard.md read/write operations
│   ├── inbox_processor.py       # Inbox triage and routing engine
│   ├── linkedin_poster.py       # LinkedIn post automation
│   └── plan_creator.py          # Plan.md generation
│
├── mcp_servers/
│   └── email_server.py          # Gmail send MCP server
│
├── scheduler/
│   ├── scheduled_tasks.py       # APScheduler task definitions
│   └── check_approvals.py       # Approval timeout checker
│
├── tests/
│   ├── test_approval.py         # 8 tests — HITL approval workflow
│   ├── test_email.py            # 8 tests — email sending
│   ├── test_linkedin.py         # 8 tests — LinkedIn integration
│   ├── test_plan.py             # 8 tests — plan creation
│   ├── test_scheduler.py        # 8 tests — scheduled tasks
│   └── test_whatsapp.py         # 8 tests — WhatsApp integration
│
├── documents/
│   ├── GMAIL_SETUP.md           # Gmail API + OAuth walkthrough
│   ├── CODE_DOCUMENTATION.md    # Full API reference
│   └── DEPLOYMENT_GUIDE.md      # New-machine deployment guide
│
├── logs/                        # Runtime logs (main.log, linkedin_posts.log)
├── main.py                      # Orchestrator — 4 threads + scheduler
├── DOCUMENTATION.md             # Complete system documentation
├── ARCHITECTURE.md              # System design + diagrams
├── BRONZE_COMPLETE.md           # Bronze completion certificate
├── SILVER_COMPLETE.md           # Silver completion certificate
└── pyproject.toml
```

---

## Agent Skills

| Skill | Trigger phrases | Output |
|-------|----------------|--------|
| `file-monitor` | *"check for new files"*, *"scan downloads"* | `FILE_*.md` in `Inbox/` |
| `gmail-monitor` | *"check gmail"*, *"check my email"* | `EMAIL_*.md` in `Inbox/` |
| `linkedin-monitor` | *"check linkedin"*, *"scan linkedin"* | `LINKEDIN_*.md` in `Inbox/` |
| `whatsapp-monitor` | *"check whatsapp"*, *"any whatsapp messages"* | `WHATSAPP_*.md` in `Inbox/` |
| `send-email` | *"send email to..."*, *"email [name]"* | Draft in `Pending_Approval/` |
| `post-linkedin` | *"post to linkedin"*, *"share update"* | Draft in `Pending_Approval/` |
| `create-plan` | *"create a plan for..."*, *"plan this task"* | `Plan.md` in `Plans/` |
| `approve-action` | *"approve [action]"*, *"yes, send it"* | Executes + moves to `Done/` |
| `reject-action` | *"reject [action]"*, *"don't send"* | Archives to `Rejected/` |
| `process-inbox` | *"process inbox"*, *"triage tasks"* | Cards routed to `Needs_Action/` or `Done/` |
| `update-dashboard` | *"update dashboard"*, *"refresh dashboard"* | `Dashboard.md` synced |
| `skill-creator` | *"create skill"*, *"make new skill"* | New `SKILL.md` from standard template |

---

## Silver Tier Requirements

| Requirement | Status |
|-------------|--------|
| All Bronze requirements | ✅ Complete |
| 4+ Watchers (File, Gmail, LinkedIn, WhatsApp) | ✅ Complete |
| LinkedIn auto-posting with HITL approval | ✅ Complete |
| Plan.md creation (reasoning loop) | ✅ Complete |
| 1+ MCP Server (email sending) | ✅ Complete |
| HITL approval workflow | ✅ Complete |
| Scheduled automation (APScheduler) | ✅ Complete |
| All AI as Agent Skills (pure markdown) | ✅ Complete |

**Requirements Met: 8/8**

---

## Project Statistics

| Metric | Value |
|--------|-------|
| Agent Skills | 12 |
| Watchers | 4 (File, Gmail, LinkedIn, WhatsApp) |
| Python modules | 11 (watchers + helpers + MCP + scheduler) |
| Scheduled tasks | 4 automated workflows |
| Vault folders | 7 |
| Test files | 6 (48 tests total) |
| Lines of code | ~5,400 (Python) + ~3,300 (Skills) |
| MCP Servers | 1 (Gmail send) |
| External APIs | 2 (Gmail OAuth2, LinkedIn via Playwright) |
| Secrets committed | 0 |

---

## Privacy & Security

| Property | Detail |
|----------|--------|
| Gmail access | `gmail.readonly` + `gmail.send` — OAuth2, tokens stored locally |
| LinkedIn access | Browser session only — no password stored, context.json git-ignored |
| WhatsApp access | Browser session only — read-only, no sending capability |
| File data stored | Filename, size, extension, timestamp — file contents never read |
| Email data stored | Sender, subject, 200-char snippet — full body never fetched |
| HITL gate | All sends and posts require explicit human approval |
| Security blacklist | `.ssh`, `.env`, `credentials`, `.pem`, `.p12` — permanently blocked |
| Storage | All data is local Markdown — nothing leaves your machine |

---

## Scheduled Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| Approval timeout check | Every hour | Auto-reject approvals older than 24h |
| Daily summary | Daily at 6 PM | Generate activity digest for the day |
| File cleanup | Sunday midnight | Archive Done/ items older than 90 days |
| Health check | Every 30 minutes | Log watcher + scheduler status |

---

## Documentation

| File | Contents |
|------|----------|
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | Complete system guide — architecture, components, data flow |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Detailed system design with ASCII diagrams |
| [`SILVER_COMPLETE.md`](SILVER_COMPLETE.md) | Silver tier completion certificate |
| [`BRONZE_COMPLETE.md`](BRONZE_COMPLETE.md) | Bronze tier completion certificate |
| [`documents/CODE_DOCUMENTATION.md`](documents/CODE_DOCUMENTATION.md) | Full API reference |
| [`documents/DEPLOYMENT_GUIDE.md`](documents/DEPLOYMENT_GUIDE.md) | Step-by-step deployment |
| [`documents/GMAIL_SETUP.md`](documents/GMAIL_SETUP.md) | Gmail API and OAuth walkthrough |

---

## Roadmap

| Tier | Status | Key additions |
|------|--------|--------------|
| **Bronze** | ✅ Complete | File + Gmail monitoring, vault pipeline, live dashboard, 5 agent skills |
| **Silver** | ✅ Complete | LinkedIn + WhatsApp monitoring, HITL approvals, MCP server, scheduled tasks, 12 skills |
| **Gold** | Planned | Autonomous loop mode, Odoo integration, multi-agent orchestration |

---

## Dependencies

```
watchdog                  6.0.0    # file system monitoring
python-frontmatter        1.1.0    # YAML frontmatter parsing
google-api-python-client  2.193.0  # Gmail API
google-auth-httplib2      0.3.1    # OAuth HTTP transport
google-auth-oauthlib      1.3.1    # OAuth browser flow
playwright                1.49.0   # LinkedIn + WhatsApp browser automation
apscheduler               3.10.4   # Background task scheduler
```

---

*AI Employee Hackathon · Silver Tier v2.0.0 · Built with Claude Code + Agent Skills*
