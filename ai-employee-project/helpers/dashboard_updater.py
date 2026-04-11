"""
helpers/dashboard_updater.py

Utilities for updating AI_Employee_Vault/Dashboard.md.

Functions
---------
get_folder_counts(vault_path)
    Scan all 7 vault folders and return accurate counts by folder and type.

update_dashboard(vault_path, activity_message, source)
    Full dashboard refresh: update activity log + all Quick Stats from real counts.

update_activity(vault_path, message)
    Prepend a timestamped entry to ## Recent Activity (cap at 20).

update_stats(vault_path, stat_name, value, operation='set')
    Update a row in the ## Quick Stats table.
    operation: 'set' sets to value, 'increment' adds value.

update_component_status(vault_path, component, status, notes='')
    Update a row in the ## System Status table.

refresh_vault_counts(vault_path)
    Recount all 7 vault folders and sync all stats (files, emails, tasks, plans, etc.).

test_dashboard_update()
    Print current vault counts and trigger a full dashboard refresh.

CLI
---
python helpers/dashboard_updater.py --activity "New file detected"
python helpers/dashboard_updater.py --stat files_monitored --value 5
python helpers/dashboard_updater.py --stat tasks_in_inbox --value 1 --operation increment
python helpers/dashboard_updater.py --component "File Monitor" --status running
python helpers/dashboard_updater.py --refresh-counts
python helpers/dashboard_updater.py --update-dashboard --activity "Manual refresh"
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
    "linkedin_checked":      "LinkedIn checked",
    "whatsapp_checked":      "WhatsApp checked",
    "plans_created":         "Plans created",
    "pending_approvals":     "Pending approvals",
    "actions_approved":      "Actions approved",
    "actions_rejected":      "Actions rejected",
}

# Maps the public component key → exact text in the System Status table
COMPONENT_NAMES: dict[str, str] = {
    "file monitor":          "File Monitor",
    "gmail monitor":         "Gmail Monitor",
    "dashboard updater":     "Dashboard Updater",
    "inbox processor":       "Inbox Processor",
    "approval checker":      "Approval Checker",
    "linkedin monitor skill": "LinkedIn Monitor Skill",
    "email mcp server":      "Email MCP Server",
    "whatsapp monitor":      "WhatsApp Monitor",
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


def get_folder_counts(vault_path: str | Path) -> dict[str, int]:
    """
    Scan all 7 vault folders and return accurate counts.

    Returns a dict with keys:
        inbox, needs_action, done, plans, pending_approval, approved, rejected
        total_files, total_emails, total_linkedin, total_whatsapp
    """
    vault = Path(vault_path)

    counts: dict[str, int] = {
        "inbox":            0,
        "needs_action":     0,
        "done":             0,
        "plans":            0,
        "pending_approval": 0,
        "approved":         0,
        "rejected":         0,
        "total_files":      0,
        "total_emails":     0,
        "total_linkedin":   0,
        "total_whatsapp":   0,
    }

    # Folder name → counts key
    folders: dict[str, str] = {
        "Inbox":            "inbox",
        "Needs_Action":     "needs_action",
        "Done":             "done",
        "Plans":            "plans",
        "Pending_Approval": "pending_approval",
        "Approved":         "approved",
        "Rejected":         "rejected",
    }

    _excluded = {"Dashboard.md", "Company_Handbook.md"}

    for folder_name, key in folders.items():
        folder_path = vault / folder_name
        if folder_path.exists():
            md_files = [
                f for f in folder_path.glob("*.md")
                if f.name not in _excluded
            ]
            counts[key] = len(md_files)

    # Count by prefix type across ALL 7 folders
    for folder_name in folders:
        folder_path = vault / folder_name
        if folder_path.exists():
            counts["total_files"]     += len(list(folder_path.glob("FILE_*.md")))
            counts["total_emails"]    += len(list(folder_path.glob("EMAIL_*.md")))
            counts["total_linkedin"]  += len(list(folder_path.glob("LINKEDIN_*.md")))
            counts["total_whatsapp"]  += len(list(folder_path.glob("WHATSAPP_*.md")))

    return counts


def update_dashboard(
    vault_path: str | Path,
    activity_message: str,
    source: str = "system",
) -> None:
    """
    Full dashboard refresh in one call:
      1. Log an activity entry.
      2. Recount all vault folders.
      3. Push every Quick Stats row with real counts.
    """
    vault_path = Path(vault_path)
    counts = get_folder_counts(vault_path)

    # 1 — activity log
    entry = f"[{source}] {activity_message}"
    update_activity(vault_path, entry)

    # 2 — per-folder task counts
    update_stats(vault_path, "tasks_in_inbox",        counts["inbox"],            "set")
    update_stats(vault_path, "tasks_in_needs_action", counts["needs_action"],     "set")
    update_stats(vault_path, "tasks_completed",       counts["done"],             "set")
    update_stats(vault_path, "plans_created",         counts["plans"],            "set")
    update_stats(vault_path, "pending_approvals",     counts["pending_approval"], "set")
    update_stats(vault_path, "actions_approved",      counts["approved"],         "set")
    update_stats(vault_path, "actions_rejected",      counts["rejected"],         "set")

    # 3 — cross-folder type counts
    update_stats(vault_path, "files_monitored",  counts["total_files"],    "set")
    update_stats(vault_path, "emails_checked",   counts["total_emails"],   "set")
    update_stats(vault_path, "linkedin_checked", counts["total_linkedin"], "set")
    update_stats(vault_path, "whatsapp_checked", counts["total_whatsapp"], "set")

    # 4 — mark Dashboard Updater itself as ONLINE
    update_component_status(vault_path, "dashboard updater", "running", "OK")

    print(
        f"[dashboard-updater] Full dashboard updated from real vault counts: "
        f"inbox={counts['inbox']}, needs_action={counts['needs_action']}, "
        f"done={counts['done']}, plans={counts['plans']}, "
        f"pending={counts['pending_approval']}, approved={counts['approved']}, "
        f"rejected={counts['rejected']}, "
        f"files={counts['total_files']}, emails={counts['total_emails']}, "
        f"linkedin={counts['total_linkedin']}, whatsapp={counts['total_whatsapp']}"
    )


def refresh_vault_counts(vault_path: str | Path) -> None:
    """
    Recount all 7 vault folders (and by-type totals) and sync every Quick Stats row.
    Use after any bulk vault operation.
    """
    vault_path = Path(vault_path)
    counts = get_folder_counts(vault_path)

    update_stats(vault_path, "tasks_in_inbox",        counts["inbox"],            "set")
    update_stats(vault_path, "tasks_in_needs_action", counts["needs_action"],     "set")
    update_stats(vault_path, "tasks_completed",       counts["done"],             "set")
    update_stats(vault_path, "plans_created",         counts["plans"],            "set")
    update_stats(vault_path, "pending_approvals",     counts["pending_approval"], "set")
    update_stats(vault_path, "actions_approved",      counts["approved"],         "set")
    update_stats(vault_path, "actions_rejected",      counts["rejected"],         "set")
    update_stats(vault_path, "files_monitored",       counts["total_files"],      "set")
    update_stats(vault_path, "emails_checked",        counts["total_emails"],     "set")
    update_stats(vault_path, "linkedin_checked",      counts["total_linkedin"],   "set")
    update_stats(vault_path, "whatsapp_checked",      counts["total_whatsapp"],   "set")

    print(
        f"[dashboard-updater] Vault counts synced — "
        f"inbox={counts['inbox']}, needs_action={counts['needs_action']}, "
        f"done={counts['done']}, plans={counts['plans']}, "
        f"pending={counts['pending_approval']}, approved={counts['approved']}, "
        f"rejected={counts['rejected']}, "
        f"files={counts['total_files']}, emails={counts['total_emails']}, "
        f"linkedin={counts['total_linkedin']}, whatsapp={counts['total_whatsapp']}"
    )


def init_component_statuses(vault_path: str | Path) -> None:
    """
    Set correct statuses for every component in the System Status table.

    Continuous monitors (File Monitor, Gmail Monitor) are left untouched —
    they self-report via their own watchers.

    On-demand components get READY; Dashboard Updater gets ONLINE because
    calling this function proves it is running.
    """
    vault_path = Path(vault_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    update_component_status(vault_path, "dashboard updater",      "running", "OK")
    update_component_status(vault_path, "inbox processor",        "ready",   "On-demand")
    update_component_status(vault_path, "linkedin monitor skill", "ready",   "On-demand")
    update_component_status(vault_path, "email mcp server",       "ready",   "On-demand")
    update_component_status(vault_path, "whatsapp monitor",       "ready",   "On-demand")

    print(f"[dashboard-updater] All component statuses initialised at {now}")


def test_dashboard_update() -> None:
    """Test dashboard update with real vault counts (prints report and refreshes)."""
    vault_path = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")

    print("Scanning vault folders...")
    counts = get_folder_counts(str(vault_path))

    print("\nCurrent Counts:")
    print(f"  Inbox:            {counts['inbox']}")
    print(f"  Needs_Action:     {counts['needs_action']}")
    print(f"  Done:             {counts['done']}")
    print(f"  Plans:            {counts['plans']}")
    print(f"  Pending_Approval: {counts['pending_approval']}")
    print(f"  Approved:         {counts['approved']}")
    print(f"  Rejected:         {counts['rejected']}")
    print(f"\nBy Type:")
    print(f"  Total Files:    {counts['total_files']}")
    print(f"  Total Emails:   {counts['total_emails']}")
    print(f"  Total LinkedIn: {counts['total_linkedin']}")
    print(f"  Total WhatsApp: {counts['total_whatsapp']}")

    update_dashboard(str(vault_path), "Manual dashboard refresh", "system")
    print("\n[OK] Dashboard updated!")


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
                       help="Recount all 7 vault folders and sync every stat row")
    group.add_argument("--update-dashboard", action="store_true",
                       help="Full refresh: log activity + recount all vault folders")
    group.add_argument("--test", action="store_true",
                       help="Run test_dashboard_update() — print counts and refresh")
    group.add_argument("--init-status", action="store_true",
                       help="Set correct status for all System Status components")

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

        elif args.update_dashboard:
            msg = args.notes if args.notes else "Manual dashboard refresh"
            update_dashboard(vault, msg, "cli")

        elif args.test:
            test_dashboard_update()

        elif args.init_status:
            init_component_statuses(vault)

    except FileNotFoundError as e:
        print(f"[dashboard-updater] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"[dashboard-updater] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
