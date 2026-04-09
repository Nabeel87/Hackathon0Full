"""
helpers/dashboard_updater.py

Utilities for updating AI_Employee_Vault/Dashboard.md.

Functions
---------
update_activity(vault_path, message)
    Prepend a timestamped entry to ## Recent Activity (cap at 20).

update_stats(vault_path, stat_name, value, operation='set')
    Update a row in the ## Quick Stats table.
    operation: 'set' sets to value, 'increment' adds value.

update_component_status(vault_path, component, status, notes='')
    Update a row in the ## System Status table.

refresh_vault_counts(vault_path)
    Recount Inbox/, Needs_Action/, Done/ and sync all task stats.

CLI
---
python helpers/dashboard_updater.py --activity "New file detected"
python helpers/dashboard_updater.py --stat files_monitored --value 5
python helpers/dashboard_updater.py --stat tasks_in_inbox --value 1 --operation increment
python helpers/dashboard_updater.py --component "File Monitor" --status running
python helpers/dashboard_updater.py --refresh-counts
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_ACTIVITY_ENTRIES = 20

# Maps the public stat_name key → exact label text in the Quick Stats table
STAT_LABELS: dict[str, str] = {
    "files_monitored":       "Files monitored",
    "emails_checked":        "Emails checked",
    "tasks_in_inbox":        "Tasks in Inbox",
    "tasks_in_needs_action": "Tasks in Needs_Action",
    "tasks_completed":       "Tasks completed",
}

# Maps the public component key → exact text in the System Status table
COMPONENT_NAMES: dict[str, str] = {
    "file monitor":       "File Monitor",
    "gmail monitor":      "Gmail Monitor",
    "dashboard updater":  "Dashboard Updater",
    "inbox processor":    "Inbox Processor",
}

# Maps CLI/code status name → display string written into the table
STATUS_DISPLAY: dict[str, str] = {
    "running":     "ONLINE",
    "online":      "ONLINE",
    "offline":     "OFFLINE",
    "not running": "OFFLINE",
    "error":       "ERROR",
    "ready":       "READY",
}


# ── File I/O ──────────────────────────────────────────────────────────────────

def _dashboard_path(vault_path: str | Path) -> Path:
    return Path(vault_path) / "Dashboard.md"


def _read(vault_path: Path) -> str:
    path = _dashboard_path(vault_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dashboard.md not found at {path}\n"
            "Ensure the vault was initialised with Dashboard.md in place."
        )
    return path.read_text(encoding="utf-8")


def _write(vault_path: Path, content: str) -> None:
    """Write Dashboard.md back to disk."""
    _dashboard_path(vault_path).write_text(content, encoding="utf-8")


def _stamp(content: str) -> str:
    """Replace ALL _Last updated:_ lines with a single current timestamp."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Remove every existing timestamp line
    content = re.sub(r"\n?_Last updated:.*?_\n?", "", content)
    # Insert one timestamp immediately after the first heading line
    content = re.sub(
        r"(# .+\n)",
        rf"\1\n_Last updated: {now}_\n",
        content,
        count=1,
    )
    return content


# ── Section helpers ───────────────────────────────────────────────────────────

def _find_section(content: str, header: str) -> tuple[int, int]:
    """
    Return (start, end) character indices of the block following `header`
    up to (but not including) the next heading of the same or higher level.
    Raises ValueError if the header is not found.
    """
    level = len(re.match(r"^(#+)", header).group(1))
    match = re.search(re.escape(header), content)
    if not match:
        raise ValueError(f"Section '{header}' not found in Dashboard.md")
    start = match.end()
    next_heading = re.search(
        r"^#{1," + str(level) + r"} ", content[start:], re.MULTILINE
    )
    end = start + next_heading.start() if next_heading else len(content)
    return start, end


# ── Public API ────────────────────────────────────────────────────────────────

def update_activity(vault_path: str | Path, message: str) -> None:
    """
    Prepend a timestamped entry to ## Recent Activity.
    Trims the list to MAX_ACTIVITY_ENTRIES.
    """
    vault_path = Path(vault_path)
    content = _read(vault_path)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"- `{now}` -- {message}"

    try:
        start, end = _find_section(content, "## Recent Activity")
    except ValueError as e:
        print(f"[dashboard-updater] WARNING: {e}")
        return

    section_text = content[start:end]
    existing = [
        line for line in section_text.splitlines()
        if line.strip().startswith("- `")
    ]

    entries = ([new_entry] + existing)[:MAX_ACTIVITY_ENTRIES]
    new_section = "\n\n" + "\n".join(entries) + "\n\n"
    content = content[:start] + new_section + content[end:]
    content = _stamp(content)
    _write(vault_path, content)
    print(f"[dashboard-updater] Activity logged: {new_entry}")


def update_stats(
    vault_path: str | Path,
    stat_name: str,
    value: int,
    operation: str = "set",
) -> None:
    """
    Update a row in the ## Quick Stats table.

    Parameters
    ----------
    stat_name : str
        One of: files_monitored, emails_checked, tasks_in_inbox,
        tasks_in_needs_action, tasks_completed
    value : int
        The numeric value to set or add.
    operation : str
        'set'       — set the cell to value
        'increment' — add value to the current cell value (minimum 0)
    """
    vault_path = Path(vault_path)

    if stat_name not in STAT_LABELS:
        raise ValueError(
            f"Unknown stat '{stat_name}'.\n"
            f"Valid names: {list(STAT_LABELS.keys())}"
        )
    if operation not in ("set", "increment"):
        raise ValueError(f"Unknown operation '{operation}'. Use 'set' or 'increment'.")

    label = STAT_LABELS[stat_name]
    content = _read(vault_path)

    row_re = re.compile(
        r"(\|\s*" + re.escape(label) + r"\s*\|\s*)(\d+)(\s*\|)",
        re.IGNORECASE,
    )
    match = row_re.search(content)
    if not match:
        print(f"[dashboard-updater] WARNING: stat row '{label}' not found in Dashboard.md")
        return

    current = int(match.group(2))
    new_value = value if operation == "set" else max(0, current + value)

    content = content[: match.start()] + match.group(1) + str(new_value) + match.group(3) + content[match.end():]
    content = _stamp(content)
    _write(vault_path, content)
    print(f"[dashboard-updater] Stat updated: {label}  {current} -> {new_value}")


def update_component_status(
    vault_path: str | Path,
    component: str,
    status: str,
    notes: str = "",
) -> None:
    """
    Update a row in the ## System Status table.

    Parameters
    ----------
    component : str
        Any of: 'File Monitor', 'Gmail Monitor', 'Dashboard Updater',
        'Inbox Processor' (case-insensitive).
    status : str
        'running' | 'online' | 'offline' | 'not running' | 'error' | 'ready'
    notes : str
        Optional short note for the Notes column.
    """
    vault_path = Path(vault_path)

    # Normalise component name
    component_key = component.lower().strip()
    # Accept exact match or prefix match
    resolved = COMPONENT_NAMES.get(component_key)
    if resolved is None:
        for key, name in COMPONENT_NAMES.items():
            if key in component_key or component_key in key:
                resolved = name
                break
    if resolved is None:
        raise ValueError(
            f"Unknown component '{component}'.\n"
            f"Valid components: {list(COMPONENT_NAMES.values())}"
        )

    status_key = status.lower().strip()
    if status_key not in STATUS_DISPLAY:
        raise ValueError(
            f"Unknown status '{status}'.\n"
            f"Valid statuses: {list(STATUS_DISPLAY.keys())}"
        )
    status_text = STATUS_DISPLAY[status_key]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_text = notes if notes else ("—" if status_key in ("offline", "not running") else "OK")

    content = _read(vault_path)

    # Match the full row for this component
    row_re = re.compile(
        r"\|\s*" + re.escape(resolved) + r"\s*\|[^\n]+",
        re.IGNORECASE,
    )
    match = row_re.search(content)
    if not match:
        print(f"[dashboard-updater] WARNING: component row '{resolved}' not found in Dashboard.md")
        return

    new_row = f"| {resolved:<16}| {status_text:<13}| {now:<16}| {note_text:<22}|"
    content = content[: match.start()] + new_row + content[match.end():]
    content = _stamp(content)
    _write(vault_path, content)
    print(f"[dashboard-updater] Status updated: {resolved} -> {status_text} at {now}")


def refresh_vault_counts(vault_path: str | Path) -> None:
    """
    Recount .md files in Inbox/, Needs_Action/, Done/ and sync stats.
    Use after any bulk vault operation.
    """
    vault_path = Path(vault_path)

    def count(folder: str) -> int:
        d = vault_path / folder
        return sum(1 for f in d.iterdir() if f.is_file() and f.suffix == ".md") if d.exists() else 0

    inbox_count        = count("Inbox")
    needs_action_count = count("Needs_Action")
    done_count         = count("Done")

    update_stats(vault_path, "tasks_in_inbox",        inbox_count,        "set")
    update_stats(vault_path, "tasks_in_needs_action", needs_action_count, "set")
    update_stats(vault_path, "tasks_completed",       done_count,         "set")

    print(
        f"[dashboard-updater] Vault counts synced: "
        f"inbox={inbox_count}, needs_action={needs_action_count}, done={done_count}"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard_updater",
        description="Update AI Employee Dashboard.md from the command line.",
    )
    parser.add_argument(
        "--vault",
        default=str(
            Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
        ),
        help="Path to the vault root (default: ~/Desktop/.../AI_Employee_Vault)",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--activity", metavar="MESSAGE",
                       help='Log an activity entry, e.g. "2 new files detected"')
    group.add_argument("--stat", metavar="STAT_NAME",
                       help=f"Stat to update. One of: {', '.join(STAT_LABELS)}")
    group.add_argument("--component", metavar="COMPONENT",
                       help='Component to update, e.g. "File Monitor"')
    group.add_argument("--refresh-counts", action="store_true",
                       help="Recount vault folders and sync all task stats")

    parser.add_argument("--value", type=int, default=0,
                        help="Value for --stat (default: 0)")
    parser.add_argument("--operation", choices=["set", "increment"], default="set",
                        help="How to apply --value: 'set' or 'increment' (default: set)")
    parser.add_argument("--status", default="running",
                        help='Status for --component: running|offline|error|ready (default: running)')
    parser.add_argument("--notes", default="",
                        help="Optional notes for --component status row")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    vault = Path(args.vault)

    try:
        if args.activity:
            update_activity(vault, args.activity)

        elif args.stat:
            update_stats(vault, args.stat, args.value, args.operation)

        elif args.component:
            update_component_status(vault, args.component, args.status, args.notes)

        elif args.refresh_counts:
            refresh_vault_counts(vault)

    except FileNotFoundError as e:
        print(f"[dashboard-updater] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"[dashboard-updater] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
