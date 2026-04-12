"""
helpers/status_updater.py

Updates task file frontmatter status as work progresses and moves
completed files to Done/.

Valid transitions
-----------------
  pending      → in_progress  (user starts working)
  in_progress  → completed    (work finished — file moved to Done/)
  pending      → blocked      (waiting on something external)
  any          → cancelled    (no longer relevant)

Functions
---------
update_task_status(vault_path, task_file, new_status, notes="")
    Core function. Finds the file, updates frontmatter, moves if completed.

mark_in_progress(vault_path, task_file)
mark_completed(vault_path, task_file)
mark_blocked(vault_path, task_file, reason="")
mark_cancelled(vault_path, task_file, reason="")
    Convenience wrappers around update_task_status().

CLI
---
    python helpers/status_updater.py LINKEDIN_20260412_message.md --status completed
    python helpers/status_updater.py GMAIL_20260412_email.md --status blocked --notes "Waiting on client reply"
"""

import sys
from pathlib import Path
from datetime import datetime

import frontmatter

# ── Project root on sys.path (for standalone execution) ───────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_VAULT_PATH = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

# All vault folders searched when locating a task file by name
VAULT_FOLDERS = [
    "Inbox",
    "Needs_Action",
    "Pending_Approval",
    "Approved",
    "Rejected",
    "Plans",
    "Archive",
    "Reports",
    "Done",
]

VALID_STATUSES = {"pending", "in_progress", "completed", "blocked", "cancelled"}


# ── Core function ─────────────────────────────────────────────────────────────

def update_task_status(
    vault_path: str | Path,
    task_file: str | Path,
    new_status: str,
    notes: str = "",
) -> bool:
    """
    Update the status field in a task file's YAML frontmatter.

    Completed tasks are automatically moved from their current folder to Done/.
    A status_history list is appended to the frontmatter on every call so the
    full audit trail is preserved inside the file.

    Args:
        vault_path: Path to AI_Employee_Vault root.
        task_file:  Filename (e.g. "LINKEDIN_20260412_message.md") or full path.
        new_status: Target status — must be one of VALID_STATUSES.
        notes:      Optional human-readable reason for the transition.

    Returns:
        True on success, False on any error.
    """
    if new_status not in VALID_STATUSES:
        print(f"Error: Invalid status '{new_status}'. Choose from: {', '.join(sorted(VALID_STATUSES))}")
        return False

    vault = Path(vault_path)
    task_file = Path(task_file)

    # ── Locate the file ───────────────────────────────────────────────────────
    if task_file.is_absolute() and task_file.exists():
        task_path = task_file
    else:
        # Search by filename across all known folders
        filename = task_file.name
        task_path = None
        for folder in VAULT_FOLDERS:
            candidate = vault / folder / filename
            if candidate.exists():
                task_path = candidate
                break

    if task_path is None:
        print(f"Error: Task file not found: {task_file.name}")
        return False

    # ── Read current frontmatter ──────────────────────────────────────────────
    try:
        post = frontmatter.load(str(task_path))
    except Exception as exc:
        print(f"Error reading {task_path.name}: {exc}")
        return False

    old_status = post.get("status", "unknown")
    now_iso = datetime.now().isoformat(timespec="seconds")

    # ── Update frontmatter fields ─────────────────────────────────────────────
    post["status"] = new_status
    post["status_updated"] = now_iso

    if "status_history" not in post:
        post["status_history"] = []

    post["status_history"].append({
        "from":      old_status,
        "to":        new_status,
        "timestamp": now_iso,
        "notes":     notes or "",
    })

    # ── Write file (move to Done/ when completed) ─────────────────────────────
    try:
        if new_status == "completed":
            done_folder = vault / "Done"
            done_folder.mkdir(parents=True, exist_ok=True)
            new_path = done_folder / task_path.name

            # Handle name collision in Done/
            counter = 1
            while new_path.exists():
                stem = task_path.stem
                new_path = done_folder / f"{stem}_{counter}{task_path.suffix}"
                counter += 1

            new_path.write_text(frontmatter.dumps(post), encoding="utf-8")
            task_path.unlink()
            print(f"Moved {task_path.name} → Done/  (status: {new_status})")
        else:
            task_path.write_text(frontmatter.dumps(post), encoding="utf-8")
            print(f"Updated {task_path.name}: {old_status} → {new_status}")
    except Exception as exc:
        print(f"Error writing {task_path.name}: {exc}")
        return False

    # ── Dashboard activity entry (best-effort) ────────────────────────────────
    try:
        from helpers.dashboard_updater import update_activity
        update_activity(
            vault,
            f"Status update: {task_path.name} → {new_status}"
            + (f" ({notes})" if notes else ""),
        )
    except Exception:
        pass

    return True


# ── Convenience wrappers ──────────────────────────────────────────────────────

def mark_in_progress(vault_path: str | Path, task_file: str | Path) -> bool:
    """Transition a task to in_progress."""
    return update_task_status(vault_path, task_file, "in_progress", "Started working on task")


def mark_completed(vault_path: str | Path, task_file: str | Path) -> bool:
    """Transition a task to completed and move it to Done/."""
    return update_task_status(vault_path, task_file, "completed", "Task completed successfully")


def mark_blocked(
    vault_path: str | Path, task_file: str | Path, reason: str = ""
) -> bool:
    """Transition a task to blocked."""
    notes = f"Blocked: {reason}" if reason else "Task blocked"
    return update_task_status(vault_path, task_file, "blocked", notes)


def mark_cancelled(
    vault_path: str | Path, task_file: str | Path, reason: str = ""
) -> bool:
    """Transition a task to cancelled."""
    notes = f"Cancelled: {reason}" if reason else "Task cancelled"
    return update_task_status(vault_path, task_file, "cancelled", notes)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        prog="status_updater",
        description="Update a vault task file's status.",
    )
    parser.add_argument("task_file", help="Task filename (e.g. LINKEDIN_20260412_message.md)")
    parser.add_argument(
        "--status",
        required=True,
        choices=sorted(VALID_STATUSES),
        help="New status to set",
    )
    parser.add_argument("--notes", default="", help="Optional reason for status change")
    parser.add_argument(
        "--vault",
        default=str(DEFAULT_VAULT_PATH),
        help=f"Vault root path (default: {DEFAULT_VAULT_PATH})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    success = update_task_status(args.vault, args.task_file, args.status, args.notes)
    sys.exit(0 if success else 1)
