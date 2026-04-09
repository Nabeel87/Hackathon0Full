---
name: file-monitor
description: "Monitors ~/Downloads/file_check/file_check for new files (privacy-safe default)"
triggers:
  - check for new files
  - monitor downloads
  - scan downloads
  - check downloads folder
config:
  monitored_folders:
    - ~/Downloads/file_check/file_check
  ignored_patterns:
    - .ssh
    - .config
    - .env
    - credentials
    - passwords
---

# Skill: file-monitor

Scans `~/Downloads/file_check` for new files, filters out anything sensitive or temporary,
and creates a structured task card in the vault Inbox for each safe file found.
Runs once per invocation — not a continuous watcher.

---

## Purpose

- Gives the AI employee visibility into files that arrive from outside (downloads, attachments, shared files)
- Converts raw file arrivals into actionable vault cards with suggested next steps
- Protects privacy by only monitoring `~/Downloads/file_check` and blocking sensitive file patterns
- Deduplicates: files already logged are silently skipped on repeat runs
- Feeds the vault pipeline — cards created here are later processed by `process-inbox`

---

## Process

1. Add the project root to the Python path so the `watchers` package is importable
2. Instantiate `FileWatcher` with `vault_path` pointing to the AI Employee Vault
3. Iterate all files in `~/Downloads/file_check` (non-recursive)
4. For each file, call `_is_safe(path)` — skip hidden files, temp files, and blacklisted patterns
5. For each safe file, build an item dict containing: `path`, `name`, `suffix`, `size_bytes`, `detected_at`
6. Call `watcher.create_action_file(item)` — this writes a `FILE_*.md` card to `Vault/Inbox/`
7. After all cards are written, invoke the `update-dashboard` skill

---

## How to Run

**Standalone (single-shot scan):**
```
cd ~/Desktop/Hackathon/Hackathon0/ai-employee-project
python watchers/file_watcher.py
```

Optional arguments:
```
python watchers/file_watcher.py <watch_dir> <vault_path>
```

**From Python (import):**
```
Project root:  ~/Desktop/Hackathon/Hackathon0/ai-employee-project
Module:        watchers.file_watcher
Class:         FileWatcher(vault_path, watch_dir)
Helper:        _is_safe(path) -> bool
Method:        create_action_file(item) -> Path
```

The script adds `PROJECT_ROOT` to `sys.path` automatically when run standalone.

---

## Security Blacklist

These patterns are always blocked — no vault card is ever created for them:

| Pattern | Reason |
|---------|--------|
| `.ssh` | SSH keys — catastrophic if exposed |
| `.config` | App credentials and personal settings |
| `.env` | Almost always contains secrets |
| `credentials` | Any file with this in the name |
| `passwords` | Any file with this in the name |
| `secret`, `private_key`, `id_rsa` | Cryptographic material |
| `.pem`, `.p12`, `.pfx` | Certificate and key files |

The blacklist checks the full file path — `~/Downloads/file_check/my-credentials-backup.csv` is also blocked.

---

## Output: Vault Card Format

Each detected file produces `Vault/Inbox/FILE_YYYYMMDD_HHMMSS_<name>.md`:

```yaml
---
type: file
file_name: "report.pdf"
file_path: "/home/user/Downloads/report.pdf"
file_size: "1230.4 KB"
file_type: ".pdf"
detected_at: "2026-04-05 14:30:22 UTC"
priority: high
status: pending
---
```

**Priority rules:**
- `high` — `.pdf`, `.docx`, `.xlsx`, `.zip`, `.exe`, or filename contains `urgent`, `invoice`, `contract`, or `payment`
- `normal` — everything else

---

## Usage Examples

> "Check for new files"
> "Scan my downloads"
> "Monitor downloads"
> "Any new files in downloads?"

**Files found:**
```
[file-monitor] Starting single-shot scan...
[file-monitor] 2 eligible file(s) found in ~/Downloads/file_check
  [new]  Card created: FILE_20260405_143022_report_pdf.md
  [new]  Card created: FILE_20260405_143022_invoice_April.md
[file-monitor] 2 new inbox card(s) created.
[file-monitor] Calling update-dashboard to refresh status...
```

**Nothing new:**
```
[file-monitor] Starting single-shot scan...
[file-monitor] 0 eligible file(s) found in ~/Downloads/file_check
[file-monitor] No new files detected.
```

---

## Dependencies

- `watchers/file_watcher.py` — provides `FileWatcher` and `_is_safe`
- `watchers/base_watcher.py` — base class, required by `file_watcher.py`
- `helpers/dashboard_updater.py` — called after scan to update activity and stats
- No third-party packages required for scanning (stdlib only: `pathlib`, `re`, `datetime`)
- `Vault/Inbox/` folder — created automatically if missing

---

## Notes

- This skill performs a point-in-time snapshot of `~/Downloads/file_check`, not live monitoring
- Files already logged (matched by name in existing vault cards) are silently skipped
- To add more monitored folders, update `config.monitored_folders` in this frontmatter and pass the additional paths to `FileWatcher`
- Executable files (`.exe`, `.dmg`) are not blocked but receive a "do not run without verifying" action checklist
- Always call `update-dashboard` after this skill to keep stats and activity log current
