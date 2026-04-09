# AI Employee — Deployment Guide

Complete step-by-step guide for deploying the AI Employee Bronze Tier system
on a new machine. Covers all operating systems. No prior experience required.

---

## Table of Contents

1. [What You Are Deploying](#1-what-you-are-deploying)
2. [Prerequisites](#2-prerequisites)
3. [Step 1 — Get the Code](#3-step-1--get-the-code)
4. [Step 2 — Create the Vault](#4-step-2--create-the-vault)
5. [Step 3 — Install Python Dependencies](#5-step-3--install-python-dependencies)
6. [Step 4 — Gmail API Setup](#6-step-4--gmail-api-setup)
7. [Step 5 — Configure Paths](#7-step-5--configure-paths)
8. [Step 6 — Verify Installation](#8-step-6--verify-installation)
9. [Step 7 — Run the System](#9-step-7--run-the-system)
10. [Step 8 — Connect Claude Code](#10-step-8--connect-claude-code)
11. [Platform-Specific Notes](#11-platform-specific-notes)
12. [Customisation](#12-customisation)
13. [Troubleshooting](#13-troubleshooting)
14. [Uninstall](#14-uninstall)

---

## 1. What You Are Deploying

The AI Employee is a local automation system that:
- Watches a folder on your machine for new files and creates task cards
- Watches your Gmail inbox for priority emails and creates task cards
- Routes all task cards through a structured vault (`Inbox` → `Needs_Action` / `Done`)
- Keeps a live `Dashboard.md` with system status, stats, and activity log
- Runs inside Claude Code using plain text "agent skills"

Everything runs locally. No cloud server, no subscription, no database.
All data is stored as plain Markdown files you can read in any text editor.

---

## 2. Prerequisites

Install these before starting.

### Required

| Tool | Minimum Version | Download |
|------|----------------|----------|
| Python | 3.10 | https://python.org/downloads |
| Git | Any recent | https://git-scm.com/downloads |
| Claude Code CLI | Latest | https://claude.ai/code |

### Recommended

| Tool | Purpose |
|------|---------|
| `uv` (Python package manager) | Faster installs, isolated environments |
| Obsidian | View the vault as a beautiful linked notebook |

### Optional (for Gmail monitoring only)

| Requirement | Details |
|-------------|---------|
| Google account | The Gmail inbox you want to monitor |
| Google Cloud project | Free — used to create API credentials |

---

### Check Python version

```bash
python --version
# or
python3 --version
```

Expected: `Python 3.10.x` or higher. If you see `3.8` or `3.9`, install a
newer version before continuing.

---

### Install uv (recommended)

**Mac / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify:
```bash
uv --version
```

---

## 3. Step 1 — Get the Code

### Option A — Clone from Git (recommended)

```bash
git clone <your-repo-url> ai-employee-project
cd ai-employee-project
```

Replace `<your-repo-url>` with the actual repository URL.

### Option B — Copy the project folder

If you received the project as a zip or folder copy:

```bash
# Place the project folder wherever you prefer, e.g.:
# ~/projects/ai-employee-project
# C:\Users\YourName\projects\ai-employee-project

cd /path/to/ai-employee-project
```

> The deployment guide uses `~/projects/ai-employee-project` as the example
> project location. Substitute your actual path everywhere below.

---

## 4. Step 2 — Create the Vault

The vault is a separate folder that stores all your task cards and the
dashboard. It lives outside the project code folder.

### Create the vault folder and subfolders

**Mac / Linux:**
```bash
mkdir -p ~/AI_Employee_Vault/Inbox
mkdir -p ~/AI_Employee_Vault/Needs_Action
mkdir -p ~/AI_Employee_Vault/Done
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\AI_Employee_Vault\Inbox"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\AI_Employee_Vault\Needs_Action"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\AI_Employee_Vault\Done"
```

### Create Dashboard.md

Create the file `~/AI_Employee_Vault/Dashboard.md` with this exact content:

```markdown
# AI Employee Dashboard

_Last updated: 2026-01-01 00:00:00_

---

## System Status

| Component        | Status        | Last Run         | Notes                  |
|------------------|---------------|------------------|------------------------|
| File Monitor     | OFFLINE       | —                | Not yet started        |
| Gmail Monitor    | OFFLINE       | —                | Not yet started        |
| Dashboard Updater| OFFLINE       | —                | Not yet started        |
| Inbox Processor  | OFFLINE       | —                | Not yet started        |

---

## Quick Stats

| Metric                    | Value |
|---------------------------|-------|
| Files monitored           | 0     |
| Emails checked            | 0     |
| Tasks in Inbox            | 0     |
| Tasks in Needs_Action     | 0     |
| Tasks completed           | 0     |

---

## Recent Activity

_No activity yet._

---

## Alerts

_No alerts._
```

### Create the watch folder

The file monitor scans this folder for new files:

**Mac / Linux:**
```bash
mkdir -p ~/Downloads/file_check
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Downloads\file_check"
```

> To use a different folder, see [Customisation → Changing the watch folder](#changing-the-watch-folder).

---

## 5. Step 3 — Install Python Dependencies

Run these commands from the project root folder.

### With uv (recommended)

```bash
cd ~/projects/ai-employee-project

uv pip install -r requirements.txt
```

Or install from `pyproject.toml`:

```bash
uv pip install .
```

### With pip (standard)

```bash
cd ~/projects/ai-employee-project

pip install -r requirements.txt
```

### Verify installation

```bash
uv run python -c "import frontmatter; print('frontmatter OK')"
uv run python -c "import googleapiclient; print('google-api OK')"
uv run python -c "import watchdog; print('watchdog OK')"
```

All three should print `OK`. If any fail, see
[Troubleshooting → ModuleNotFoundError](#modulenotfounderror).

---

## 6. Step 4 — Gmail API Setup

Skip this step if you only want to use file monitoring.

### 6.1 Create a Google Cloud project

1. Open https://console.cloud.google.com in your browser
2. Sign in with the Google account whose Gmail you want to monitor
3. Click **"Select a project"** (top bar) → **"New Project"**
4. Project name: `ai-employee` → click **Create**
5. Wait for the project to provision (~10 seconds)
6. Ensure the new project is selected in the top bar

### 6.2 Enable the Gmail API

1. In the left sidebar: **APIs & Services** → **Library**
2. Search for `Gmail API`
3. Click the **Gmail API** card → click **Enable**

### 6.3 Configure the OAuth consent screen

1. **APIs & Services** → **OAuth consent screen**
2. Select **External** → click **Create**
3. Fill in:
   - **App name:** `AI Employee`
   - **User support email:** your Gmail address
   - **Developer contact email:** your Gmail address
4. Click **Save and Continue** through the remaining pages
5. On the **Test users** page, click **+ Add Users**
6. Enter the Gmail address you want to monitor → **Add**
7. Click **Save and Continue** → **Back to Dashboard**

### 6.4 Create OAuth credentials

1. **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `ai-employee-desktop` → click **Create**
5. Click **Download JSON**
6. The file downloads as `client_secret_<long-id>.json`

### 6.5 Install the credentials file

```bash
# Create the credentials folder
mkdir -p ~/projects/ai-employee-project/.credentials

# Rename and move the downloaded file
# Mac/Linux:
mv ~/Downloads/client_secret_*.json ~/projects/ai-employee-project/.credentials/credentials.json

# Windows (PowerShell) — adjust the filename to match your download:
Move-Item "$env:USERPROFILE\Downloads\client_secret_*.json" `
          "$env:USERPROFILE\projects\ai-employee-project\.credentials\credentials.json"
```

Verify:
```bash
ls ~/projects/ai-employee-project/.credentials/
# Expected:  credentials.json
```

### 6.6 First-run authorisation

The first time the Gmail monitor runs it will open your browser to grant
permission. This happens automatically — no extra steps needed now.

---

## 7. Step 5 — Configure Paths

The default paths assume this layout:

```
~/
├── Downloads/
│   └── file_check/          ← drop files here to be monitored
├── AI_Employee_Vault/        ← vault folder
└── projects/
    └── ai-employee-project/  ← code folder
```

If your paths are different, update these two places:

### 7.1 main.py — default vault path

Open `main.py` and find (around line 325):

```python
parser.add_argument(
    "--vault-path",
    default=str(Path.home() / "Desktop/Hackathon/Hackathon0/AI_Employee_Vault"),
    ...
)
```

Change the default to your vault location:

```python
default=str(Path.home() / "AI_Employee_Vault"),
```

### 7.2 Skill config blocks

Update the `config:` blocks in each SKILL.md:

**`.claude/skills/file-monitor/SKILL.md`:**
```yaml
config:
  monitored_folders:
    - ~/Downloads/file_check    # ← change this
```

**`.claude/skills/gmail-monitor/SKILL.md`:**
```yaml
config:
  credentials_dir: ~/projects/ai-employee-project/.credentials  # ← change this
  vault_inbox: ~/AI_Employee_Vault/Inbox                         # ← change this
```

**`.claude/skills/process-inbox/SKILL.md`:**
```yaml
config:
  vault_root: ~/AI_Employee_Vault       # ← change this
  inbox_dir: ~/AI_Employee_Vault/Inbox  # ← change this
```

**`.claude/skills/update-dashboard/SKILL.md`:**
```yaml
config:
  dashboard_path: ~/AI_Employee_Vault/Dashboard.md  # ← change this
```

> **Tip:** If you always run `main.py` with `--vault-path`, you don't need to
> change anything in the skill files — just pass the correct path at runtime.

---

## 8. Step 6 — Verify Installation

Run the standalone test suite to confirm everything is wired up.

### Test 1 — File watcher (no credentials required)

```bash
cd ~/projects/ai-employee-project

# Create a test file in the watch folder
echo "test content" > ~/Downloads/file_check/test_invoice.txt

# Run the file watcher standalone
uv run python watchers/file_watcher.py ~/Downloads/file_check ~/AI_Employee_Vault
```

Expected output:
```
[FileWatcher] Starting FileWatcher (interval=60s, vault=~/AI_Employee_Vault)
[FileWatcher] 1 new item(s) found.
[FileWatcher] Action file created: FILE_20260406_120000_test_invoice_txt.md
```

Check the vault:
```bash
ls ~/AI_Employee_Vault/Inbox/
# Expected: FILE_20260406_120000_test_invoice_txt.md
```

### Test 2 — Dashboard updater

```bash
uv run python helpers/dashboard_updater.py \
    --vault ~/AI_Employee_Vault \
    --activity "Deployment test successful"
```

Expected output:
```
[dashboard-updater] Activity logged: - `2026-04-06 12:00` -- Deployment test successful
```

Open `~/AI_Employee_Vault/Dashboard.md` — you should see the activity entry.

### Test 3 — Inbox processor

```bash
uv run python helpers/inbox_processor.py --vault ~/AI_Employee_Vault
```

Expected output:
```
[inbox-processor] Found 1 card(s) in Inbox.
  [needs_action] FILE_20260406_120000_test_invoice_txt.md
                 reason: document (.txt)
[inbox-processor] Processed 1 file(s)
  Moved to Needs_Action : 1
  Moved to Done         : 0
```

### Test 4 — Gmail watcher (requires credentials)

```bash
uv run python watchers/gmail_watcher.py ~/AI_Employee_Vault
```

On first run: a browser window opens for Gmail authorisation. Complete it.
After authorisation, you will see:
```
[GmailWatcher] Token saved to .credentials/token.json
[GmailWatcher] Query: is:unread (label:inbox OR label:important) ("urgent" OR ...)
[GmailWatcher] No new items.   ← or a count of matched emails
```

---

## 9. Step 7 — Run the System

### Option A — Orchestrator (recommended for continuous monitoring)

The orchestrator runs both watchers in parallel threads indefinitely.

```bash
cd ~/projects/ai-employee-project

# Default paths (after you updated main.py):
uv run python main.py

# Or specify all paths explicitly:
uv run python main.py \
    --vault-path ~/AI_Employee_Vault \
    --file-interval 60 \
    --gmail-interval 300 \
    --log-level INFO
```

To stop: press `CTRL+C`. The orchestrator shuts down gracefully.

**Logs are written to:** `~/projects/ai-employee-project/logs/main.log`

### Option B — Individual watchers (for testing or on-demand use)

```bash
# File watcher only:
uv run python watchers/file_watcher.py

# Gmail watcher only:
uv run python watchers/gmail_watcher.py

# Process inbox only:
uv run python helpers/inbox_processor.py --vault ~/AI_Employee_Vault
```

### Option C — Background process (keep running after terminal closes)

**Mac / Linux (nohup):**
```bash
nohup uv run python main.py \
    --vault-path ~/AI_Employee_Vault > logs/nohup.log 2>&1 &

echo "PID: $!"  # save this to kill later
```

To stop:
```bash
kill <PID>
```

**Windows (background job via PowerShell):**
```powershell
Start-Process -NoNewWindow -FilePath "uv" `
    -ArgumentList "run python main.py --vault-path $env:USERPROFILE\AI_Employee_Vault" `
    -RedirectStandardOutput "logs\stdout.log" `
    -RedirectStandardError "logs\stderr.log"
```

---

## 10. Step 8 — Connect Claude Code

Claude Code reads the `.claude/skills/` folder automatically when launched from
the project directory.

```bash
cd ~/projects/ai-employee-project
claude
```

### Triggering skills in Claude Code

Once Claude Code is open, use these natural language phrases:

| What you want | What to say |
|---------------|-------------|
| Scan for new files | `"check for new files"` or `"scan downloads"` |
| Check Gmail | `"check gmail"` or `"check my email"` |
| Process inbox | `"process inbox"` or `"triage tasks"` |
| Refresh dashboard | `"update dashboard"` or `"refresh dashboard"` |
| Full cycle | `"check for new files and emails, then process everything"` |

### Example session

```
You:    Check for new files
Claude: [runs file-monitor]
        Found 2 new file(s) in ~/Downloads/file_check:
        • FILE_20260406_143022_report_pdf.md — created
        • FILE_20260406_143022_invoice_April.md — created
        Dashboard updated.

You:    Check my email
Claude: [runs gmail-monitor]
        Authenticated successfully (token refreshed).
        1 priority email found:
        • EMAIL_20260406_143055_1a2b3c4d_Invoice_April_services.md — created

You:    Process inbox
Claude: [runs process-inbox]
        3 cards processed:
        • 3 → Needs_Action (2 documents, 1 invoice email)
        • 0 → Done
        Dashboard updated. Vault counts synced.
```

---

## 11. Platform-Specific Notes

### Windows

**Path format in Python:** The code uses `pathlib.Path` throughout, which
handles Windows paths correctly. Always use `uv run python` rather than bare
`python` to ensure the right interpreter is used.

**Home directory:** `Path.home()` resolves to `C:\Users\<YourName>` on Windows.
So `~/AI_Employee_Vault` means `C:\Users\<YourName>\AI_Employee_Vault`.

**Hidden folders:** `.credentials/` and `.claude/` start with a dot. On
Windows these are visible in Explorer by default. Do not delete them.

**SIGTERM:** Windows does not support `SIGTERM`. The orchestrator catches
`SIGINT` (CTRL+C) for graceful shutdown. `SIGTERM` handling is included for
Linux compatibility but has no effect on Windows.

---

### macOS

**Python 3.10+:** macOS ships with Python 2 or 3.9 on older systems. Use
`python3` explicitly or install via Homebrew:

```bash
brew install python@3.12
```

**Google auth browser:** The OAuth flow calls `webbrowser.open()` — on macOS
this opens your default browser automatically.

---

### Linux

**Browser for OAuth:** Ensure a graphical browser is available. On headless
servers the OAuth flow will print a URL to the terminal — copy and open it
manually in a browser on another machine, then paste the authorisation code
back.

**Cron integration (optional):**
```bash
# Run orchestrator at system startup (add to crontab):
@reboot cd /home/user/projects/ai-employee-project && uv run python main.py --vault-path ~/AI_Employee_Vault >> logs/cron.log 2>&1
```

---

## 12. Customisation

### Changing the watch folder

Edit `watchers/file_watcher.py` line 65:

```python
# Before:
self.watch_dir = Path(watch_dir) if watch_dir else Path.home() / "Downloads/file_check"

# After — change to any folder:
self.watch_dir = Path(watch_dir) if watch_dir else Path("/path/to/your/folder")
```

Or pass it at runtime:

```bash
uv run python watchers/file_watcher.py /path/to/folder ~/AI_Employee_Vault
```

---

### Adding Gmail search keywords

Edit `watchers/gmail_watcher.py` line 25:

```python
# Before:
KEYWORDS = ["urgent", "asap", "invoice", "payment"]

# After — add any keywords:
KEYWORDS = ["urgent", "asap", "invoice", "payment", "contract", "deadline"]
```

Also update `config.keywords` in `.claude/skills/gmail-monitor/SKILL.md` to
keep the skill documentation in sync.

---

### Changing poll intervals

```bash
# Check files every 30 seconds, Gmail every 5 minutes:
uv run python main.py --file-interval 30 --gmail-interval 300
```

Or change the defaults in `main.py` around line 330:

```python
parser.add_argument("--file-interval", type=int, default=30, ...)
parser.add_argument("--gmail-interval", type=int, default=300, ...)
```

---

### Customising routing rules

Edit `helpers/inbox_processor.py`:

```python
# Add more extensions that auto-go to Done (auto-discard):
DISCARD_EXTENSIONS = {".tmp", ".temp", ".bak", ".log", ".cache"}

# Add more name hints that auto-go to Done:
DISCARD_NAME_HINTS = ["test", "temp", "delete", "draft", "old"]
```

---

### Using a different vault location

Pass `--vault-path` to the orchestrator:

```bash
uv run python main.py --vault-path /path/to/your/vault
```

Or update the default in `main.py`:

```python
default=str(Path.home() / "AI_Employee_Vault"),
```

---

## 13. Troubleshooting

### `ModuleNotFoundError: No module named 'frontmatter'`

You are using the wrong Python interpreter (not the uv environment).

```bash
# Always use uv run:
uv run python watchers/file_watcher.py

# Reinstall if the module is genuinely missing:
uv pip install python-frontmatter
```

---

### `FileNotFoundError: credentials.json not found`

The Gmail credentials file is missing or in the wrong location.

```bash
ls ~/projects/ai-employee-project/.credentials/
# Expected output: credentials.json
```

If missing, repeat [Step 4 — Gmail API Setup](#6-step-4--gmail-api-setup).

---

### `google.auth.exceptions.RefreshError: Token has been expired or revoked`

Your Gmail access token has been revoked. Delete it and re-authorise:

```bash
rm ~/projects/ai-employee-project/.credentials/token.json
uv run python watchers/gmail_watcher.py
```

The browser flow will run once to create a new `token.json`.

---

### `FileNotFoundError: Dashboard.md not found`

The vault was not set up correctly.

```bash
ls ~/AI_Employee_Vault/
# Expected: Dashboard.md  Inbox/  Needs_Action/  Done/
```

If missing, go back to [Step 2 — Create the Vault](#4-step-2--create-the-vault).

---

### File cards not appearing in Inbox

Check that the watch folder exists and contains files:

```bash
ls ~/Downloads/file_check/
```

If empty, copy a test file there and re-run:

```bash
echo "test" > ~/Downloads/file_check/test.txt
uv run python watchers/file_watcher.py
```

If the file already has a card in `Inbox/`, `Needs_Action/`, or `Done/`, it
will be skipped (deduplication). Delete the existing card to re-process.

---

### "Access blocked: This app's request is invalid" (Gmail)

Your Gmail address is not in the test users list.

1. Go to Google Cloud Console → **APIs & Services** → **OAuth consent screen**
2. Click **Edit App**
3. On the **Test users** step, add your Gmail address
4. Save, then try again

---

### `This app isn't verified` warning in browser (Gmail)

This is expected for personal/test apps. Click:
**Advanced** → **Go to AI Employee (unsafe)** → grant permission.

To permanently remove the warning you would need to submit the app for Google
verification — not required for personal use.

---

### Dashboard stats look wrong after a bulk operation

Run a full vault count resync:

```bash
uv run python helpers/dashboard_updater.py \
    --vault ~/AI_Employee_Vault \
    --refresh-counts
```

---

### Orchestrator crashes on startup

Check `logs/main.log` for the error:

```bash
tail -50 ~/projects/ai-employee-project/logs/main.log
```

Common causes:
- Wrong vault path (check with `--vault-path`)
- Missing Python dependencies (re-run `uv pip install -r requirements.txt`)
- `credentials.json` missing (Gmail watcher init fails — file monitor will
  still run)

---

### On Windows: `python` is not recognised

```powershell
# Use the full path or ensure Python is on PATH:
py -3 -m pip install -r requirements.txt
py -3 main.py

# Or use uv which handles this automatically:
uv run python main.py
```

---

## 14. Uninstall

To remove the AI Employee system:

1. **Stop the orchestrator** — press CTRL+C in the terminal where it is running

2. **Remove the project folder:**
   ```bash
   rm -rf ~/projects/ai-employee-project
   ```

3. **Remove the vault** (if you no longer need the task cards):
   ```bash
   rm -rf ~/AI_Employee_Vault
   ```

4. **Remove the watch folder** (optional):
   ```bash
   rm -rf ~/Downloads/file_check
   ```

5. **Revoke Gmail access** (recommended):
   - Go to https://myaccount.google.com/permissions
   - Find **AI Employee** → click **Remove Access**

6. **Delete the Google Cloud project** (optional):
   - Go to Google Cloud Console → select `ai-employee` project
   - **IAM & Admin** → **Settings** → **Shut down project**

---

## Quick Reference Card

```
DEPLOY CHECKLIST
────────────────────────────────────────────────────
[ ] Python 3.10+ installed          python3 --version
[ ] uv installed                    uv --version
[ ] Claude Code installed           claude --version
[ ] Project folder in place         ls ~/projects/ai-employee-project/
[ ] Vault folders created           ls ~/AI_Employee_Vault/
[ ] Dashboard.md created            cat ~/AI_Employee_Vault/Dashboard.md
[ ] Watch folder created            ls ~/Downloads/file_check/
[ ] Dependencies installed          uv pip install -r requirements.txt
[ ] credentials.json in place       ls .credentials/    (Gmail only)
[ ] Path defaults updated           grep "vault" main.py
[ ] File watcher test passed        uv run python watchers/file_watcher.py
[ ] Dashboard test passed           uv run python helpers/dashboard_updater.py --refresh-counts
[ ] Inbox processor test passed     uv run python helpers/inbox_processor.py
[ ] Gmail test passed               uv run python watchers/gmail_watcher.py  (Gmail only)
[ ] Orchestrator running            uv run python main.py
[ ] Claude Code connected           claude (from project folder)
────────────────────────────────────────────────────

USEFUL COMMANDS
────────────────────────────────────────────────────
Start orchestrator:   uv run python main.py --vault-path ~/AI_Employee_Vault
View logs:            tail -f logs/main.log
Resync dashboard:     uv run python helpers/dashboard_updater.py --vault ~/AI_Employee_Vault --refresh-counts
Process inbox:        uv run python helpers/inbox_processor.py --vault ~/AI_Employee_Vault
Reset Gmail token:    rm .credentials/token.json
────────────────────────────────────────────────────
```

---

*Deployment Guide — AI Employee Bronze Tier — 2026-04-06*
