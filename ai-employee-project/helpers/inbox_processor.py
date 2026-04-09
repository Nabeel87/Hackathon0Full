"""
helpers/inbox_processor.py

Processes all .md task cards in Vault/Inbox/, routes each one to
Needs_Action/ or Done/ based on frontmatter content, then syncs
Dashboard.md via dashboard_updater.

Usage
-----
From Python:
    from helpers.inbox_processor import process_inbox
    summary = process_inbox(vault_path)

CLI:
    python helpers/inbox_processor.py
    python helpers/inbox_processor.py --vault /path/to/vault
"""

import argparse
import shutil
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import frontmatter

from helpers.dashboard_updater import (
    refresh_vault_counts,
    update_activity,
    update_component_status,
)

# ── Routing config ────────────────────────────────────────────────────────────

DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls"}
IMAGE_EXTENSIONS    = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
ARCHIVE_EXTENSIONS  = {".zip", ".tar", ".gz", ".rar", ".7z"}
EXEC_EXTENSIONS     = {".exe", ".msi", ".dmg", ".pkg", ".sh"}
DISCARD_EXTENSIONS  = {".tmp", ".temp", ".bak"}
DISCARD_NAME_HINTS  = ["test", "temp", "delete"]


# ── Routing logic ─────────────────────────────────────────────────────────────

def _route_file(post: frontmatter.Post, card_path: Path) -> tuple[str, str]:
    """
    Decide destination for a type=file card.
    Returns ('needs_action' | 'done', reason).
    """
    ext       = str(post.get("file_type", "")).lower()
    file_name = str(post.get("file_name", card_path.name)).lower()

    # Auto-discard: temp/test artefacts
    if ext in DISCARD_EXTENSIONS:
        return "done", f"auto-discarded (temp extension: {ext})"
    if any(hint in file_name for hint in DISCARD_NAME_HINTS):
        return "done", f"auto-discarded (name hint: {file_name})"

    # Everything else needs human review
    if ext in DOCUMENT_EXTENSIONS:
        return "needs_action", f"document ({ext})"
    if ext in IMAGE_EXTENSIONS:
        return "needs_action", f"image ({ext})"
    if ext in ARCHIVE_EXTENSIONS:
        return "needs_action", f"archive ({ext})"
    if ext in EXEC_EXTENSIONS:
        return "needs_action", f"executable ({ext}) — requires manual review"
    return "needs_action", f"unknown type ({ext}) — safe default"


def _route_email(post: frontmatter.Post) -> tuple[str, str]:
    """
    Decide destination for a type=email card.
    All emails go to needs_action — no email is ever auto-discarded.
    """
    priority = str(post.get("priority", "normal")).lower()
    subject  = str(post.get("subject",  "")).lower()

    if priority == "high":
        return "needs_action", "high priority"
    if any(kw in subject for kw in ["urgent", "asap"]):
        return "needs_action", "urgent keyword in subject"
    if any(kw in subject for kw in ["invoice", "payment"]):
        return "needs_action", "financial keyword in subject"
    return "needs_action", "standard review required"


def _route(post: frontmatter.Post, card_path: Path) -> tuple[str, str]:
    """Dispatch to the correct routing function based on task type."""
    task_type = str(post.get("type", "")).lower()
    if task_type in ("file", "file_drop"):
        return _route_file(post, card_path)
    if task_type == "email":
        return _route_email(post)
    return "needs_action", f"unknown type '{task_type}' — manual triage"


# ── File move ─────────────────────────────────────────────────────────────────

def _move(src: Path, dest_dir: Path) -> Path:
    """
    Move src to dest_dir. Appends _1, _2 … if a filename conflict exists.
    Returns the final destination path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    if dest.exists():
        stem, suffix = src.stem, src.suffix
        i = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{i}{suffix}"
            i += 1

    shutil.move(str(src), str(dest))
    return dest


# ── Main function ─────────────────────────────────────────────────────────────

def process_inbox(vault_path: str | Path) -> dict:
    """
    Scan Vault/Inbox/, route every .md card, move files, update dashboard.

    Returns
    -------
    dict with keys:
        processed       int   — total cards handled
        to_needs_action int   — cards moved to Needs_Action/
        to_done         int   — cards moved to Done/
        errors          list  — list of (filename, error_message) tuples
    """
    vault_path       = Path(vault_path)
    inbox_dir        = vault_path / "Inbox"
    needs_action_dir = vault_path / "Needs_Action"
    done_dir         = vault_path / "Done"

    summary = {
        "processed":       0,
        "to_needs_action": 0,
        "to_done":         0,
        "errors":          [],
    }

    if not inbox_dir.exists():
        print(f"[inbox-processor] Inbox folder not found: {inbox_dir}")
        return summary

    cards = sorted(f for f in inbox_dir.iterdir() if f.is_file() and f.suffix == ".md")

    if not cards:
        print("[inbox-processor] Inbox is empty - nothing to process.")
        return summary

    print(f"[inbox-processor] Found {len(cards)} card(s) in Inbox.\n")

    for card in cards:
        # ── Parse frontmatter ─────────────────────────────────────────────
        try:
            post = frontmatter.load(str(card))
        except Exception as e:
            msg = f"frontmatter parse error: {e}"
            print(f"  [error] {card.name}: {msg}")
            summary["errors"].append((card.name, msg))
            continue

        # ── Route ─────────────────────────────────────────────────────────
        destination_key, reason = _route(post, card)
        dest_dir   = needs_action_dir if destination_key == "needs_action" else done_dir
        dest_label = "Needs_Action" if destination_key == "needs_action" else "Done"

        # ── Move ──────────────────────────────────────────────────────────
        try:
            _move(card, dest_dir)
        except Exception as e:
            msg = f"move failed: {e}"
            print(f"  [error] {card.name}: {msg}")
            summary["errors"].append((card.name, msg))
            continue

        summary["processed"] += 1
        if destination_key == "needs_action":
            summary["to_needs_action"] += 1
            print(f"  [needs_action] {card.name}")
        else:
            summary["to_done"] += 1
            print(f"  [done]         {card.name}")
        print(f"                 reason: {reason}")

    # ── Dashboard update ──────────────────────────────────────────────────
    _print_summary(summary)

    try:
        na  = summary["to_needs_action"]
        dn  = summary["to_done"]
        msg = f"process-inbox: {summary['processed']} card(s) processed"
        if na:
            msg += f", {na} to Needs_Action"
        if dn:
            msg += f", {dn} to Done"

        update_activity(vault_path, msg)
        refresh_vault_counts(vault_path)
        update_component_status(vault_path, "Inbox Processor", "online")
        print("[inbox-processor] Dashboard updated.")
    except Exception as e:
        print(f"[inbox-processor] WARNING: dashboard update failed: {e}")

    return summary


def _print_summary(summary: dict) -> None:
    line = "-" * 50
    print(f"\n{line}")
    print(f"[inbox-processor] Processed {summary['processed']} file(s)")
    print(f"  Moved to Needs_Action : {summary['to_needs_action']}")
    print(f"  Moved to Done         : {summary['to_done']}")
    if summary["errors"]:
        print(f"  Errors                : {len(summary['errors'])}")
        for name, msg in summary["errors"]:
            print(f"    - {name}: {msg}")
    print(line)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="inbox_processor",
        description="Process Vault/Inbox/ cards and route them to Needs_Action/ or Done/.",
    )
    parser.add_argument(
        "--vault",
        default=str(
            Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
        ),
        help="Path to the vault root (default: ~/Desktop/.../AI_Employee_Vault)",
    )
    args = parser.parse_args()

    summary = process_inbox(args.vault)
    if summary["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    main()
