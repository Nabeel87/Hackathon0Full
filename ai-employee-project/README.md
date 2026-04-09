# AI Employee

![Bronze Tier](https://img.shields.io/badge/Tier-Bronze%20Complete-CD7F32?style=for-the-badge&logo=checkmarx&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-6B46C1?style=for-the-badge&logo=anthropic&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-8%2F8%20Passing-22C55E?style=for-the-badge)

> An autonomous, privacy-respecting AI employee that monitors your files and
> inbox, creates structured task cards, and maintains a live dashboard —
> running entirely on your local machine with zero cloud infrastructure.

---

## What It Does

| Capability | Detail |
|-----------|--------|
| **File monitoring** | Watches `~/Downloads/file_check` for new files — creates a structured task card for each one |
| **Gmail monitoring** | Scans Gmail (read-only) for unread emails matching `urgent`, `asap`, `invoice`, `payment` |
| **Task routing** | Routes every card through `Inbox → Needs_Action → Done` with rule-based triage |
| **Live dashboard** | `Dashboard.md` tracks system status, counters, and a timestamped activity log |
| **Agent Skills** | Natural-language trigger phrases via Claude Code — no commands to memorise |

---

## Architecture

```
  AGENT SKILLS LAYER  (.claude/skills/)
  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────┐
  │file-monitor │ │gmail-monitor │ │process-inbox │ │update-dashboard│
  └──────┬──────┘ └──────┬───────┘ └──────┬───────┘ └───────┬────────┘
         │               │                │                  │
  PYTHON LAYER  (watchers/ + helpers/ + main.py)
  ┌────────────────────┐  ┌─────────────────────┐  ┌───────────────────┐
  │  file_watcher.py   │  │  inbox_processor.py │  │ dashboard_updater │
  │  gmail_watcher.py  │  │  (routing engine)   │  │ (reads/writes .md)│
  └─────────┬──────────┘  └─────────────────────┘  └───────────────────┘
            │   main.py orchestrates both watchers in parallel threads
  VAULT  (AI_Employee_Vault/)
  ┌──────────┐    ┌──────────────┐    ┌─────────┐    ┌──────────────┐
  │  Inbox/  │ →  │Needs_Action/ │ →  │  Done/  │    │ Dashboard.md │
  │FILE_*.md │    │ (review me)  │    │(archive)│    │  (live view) │
  │EMAIL_*.md│    └──────────────┘    └─────────┘    └──────────────┘
  └──────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Claude Code](https://claude.ai/code)

### 1 — Clone and install

```bash
git clone <repo-url> ai-employee-project
cd ai-employee-project
uv pip install -r requirements.txt
```

### 2 — Create the vault

```bash
mkdir -p ~/AI_Employee_Vault/{Inbox,Needs_Action,Done}
mkdir -p ~/Downloads/file_check
```

Copy the `Dashboard.md` template from [`documents/DEPLOYMENT_GUIDE.md`](documents/DEPLOYMENT_GUIDE.md#4-step-2--create-the-vault).

### 3 — Gmail setup *(skip if you only need file monitoring)*

Full walkthrough: [`documents/GMAIL_SETUP.md`](documents/GMAIL_SETUP.md)

Short version: Google Cloud Console → create project → enable Gmail API →
create OAuth Desktop credentials → save `credentials.json` to `.credentials/`.

### 4 — Start the orchestrator

```bash
uv run python main.py --vault-path ~/AI_Employee_Vault
```

### 5 — Open Claude Code and talk to it

```bash
cd ai-employee-project
claude
```

```
"check for new files"    →  scans ~/Downloads/file_check, creates FILE_*.md cards
"check my email"         →  queries Gmail, creates EMAIL_*.md cards
"process inbox"          →  routes all cards to Needs_Action/ or Done/
"update dashboard"       →  refreshes stats and activity log
```

---

## Folder Structure

```
ai-employee-project/
├── .claude/skills/            # Agent Skills — plain Markdown instructions
│   ├── file-monitor/          # Scans filesystem for new files
│   ├── gmail-monitor/         # Queries Gmail for priority emails
│   ├── process-inbox/         # Routes Inbox cards
│   ├── update-dashboard/      # Refreshes Dashboard.md
│   └── skill-creator/         # Meta-skill: generates new skills from template
├── watchers/
│   ├── base_watcher.py        # Abstract base — shared polling loop
│   ├── file_watcher.py        # Filesystem scanner + card writer
│   └── gmail_watcher.py       # Gmail API client + OAuth flow
├── helpers/
│   ├── dashboard_updater.py   # All Dashboard.md read/write operations
│   └── inbox_processor.py     # Inbox triage and routing engine
├── documents/
│   ├── GMAIL_SETUP.md         # Step-by-step Gmail API setup
│   ├── CODE_DOCUMENTATION.md  # Full API reference for every module
│   └── DEPLOYMENT_GUIDE.md    # New-machine deployment guide
├── logs/                      # Runtime logs (main.log)
├── main.py                    # Orchestrator — threaded, auto-restart
├── DOCUMENTATION.md           # Complete system documentation
├── BRONZE_COMPLETE.md         # Completion certificate + test results
└── pyproject.toml
```

---

## Agent Skills

| Skill | Trigger phrases | Output |
|-------|----------------|--------|
| `file-monitor` | *"check for new files"*, *"scan downloads"* | `FILE_*.md` cards in `Inbox/` |
| `gmail-monitor` | *"check gmail"*, *"check my email"* | `EMAIL_*.md` cards in `Inbox/` |
| `process-inbox` | *"process inbox"*, *"triage tasks"* | Cards routed to `Needs_Action/` or `Done/` |
| `update-dashboard` | *"update dashboard"*, *"refresh dashboard"* | `Dashboard.md` synced |
| `skill-creator` | *"create skill"*, *"make new skill"* | New `SKILL.md` from standard template |

---

## Privacy & Security

| Property | Detail |
|----------|--------|
| Gmail access | `gmail.readonly` scope — cannot send, delete, or modify any email |
| File data stored | Filename, size, extension, timestamp only — file contents never read |
| Email data stored | Sender, subject, 200-char snippet only — full body never fetched |
| Security blacklist | `.ssh`, `.env`, `credentials`, `passwords`, `secret`, `.pem`, `.p12` — permanently blocked |
| Storage | All data is local Markdown files — nothing leaves your machine |
| Credentials | `credentials.json` and `token.json` are in `.credentials/` and git-ignored |

---

## Documentation

| File | Contents |
|------|----------|
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | Complete guide — architecture, components, data flow, full worked example |
| [`documents/CODE_DOCUMENTATION.md`](documents/CODE_DOCUMENTATION.md) | API reference for every module, class, and function |
| [`documents/DEPLOYMENT_GUIDE.md`](documents/DEPLOYMENT_GUIDE.md) | Step-by-step deployment for any machine |
| [`documents/GMAIL_SETUP.md`](documents/GMAIL_SETUP.md) | Gmail API and OAuth setup walkthrough |
| [`BRONZE_COMPLETE.md`](BRONZE_COMPLETE.md) | Completion certificate and test results |

---

## Roadmap

| Tier | Status | Key additions |
|------|--------|--------------|
| **Bronze** | ✅ Complete | File + Gmail monitoring, vault pipeline, live dashboard, 5 agent skills |
| **Silver** | 🔲 Planned | Scheduled automation, Google Calendar, Slack alerts, smart summaries |
| **Gold** | 🔲 Planned | HITL approval workflow, Odoo integration, autonomous loop mode |

---

## Dependencies

```
watchdog                  6.0.0    # file system monitoring
python-frontmatter        1.1.0    # YAML frontmatter parsing
google-api-python-client  2.193.0  # Gmail API
google-auth-httplib2      0.3.1    # OAuth HTTP transport
google-auth-oauthlib      1.3.1    # OAuth browser flow
```

---

*AI Employee Hackathon · Bronze Tier v0.1.0 · Built with Claude Code + Agent Skills*
