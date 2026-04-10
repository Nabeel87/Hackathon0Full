"""
scheduler/check_approvals.py

Scans AI_Employee_Vault/Pending_Approval/ for expired approval files and
auto-rejects them.  Intended to run periodically via cron or APScheduler.

Every expired file is:
  1. Updated with status/rejected_by/rejected_at/rejection_reason frontmatter
  2. Appended with an ## AUTO-REJECTION (TIMEOUT) section
  3. Moved from Pending_Approval/ to Rejected/
  4. Logged in logs/approvals.log (two lines: AUTO_REJECTED + REASON)
  5. Reflected in Dashboard.md via dashboard_updater

Usage
-----
From Python:
    from scheduler.check_approvals import check_pending_approvals
    result = check_pending_approvals(vault_path)

CLI:
    python scheduler/check_approvals.py
    python scheduler/check_approvals.py --vault /path/to/vault
    python scheduler/check_approvals.py --dry-run --verbose
    python scheduler/check_approvals.py --warn-hours 2

Cron (hourly):
    0 * * * * cd /path/to/project && python scheduler/check_approvals.py
"""

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import frontmatter

from helpers.dashboard_updater import (
    update_activity,
    update_component_status,
    update_stats,
)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

LOG_DIR  = _PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "approvals.log"

TIMEOUT_REASON = "Approval timeout (24 hours expired)"

# Sentinel so callers can detect a missing/unparseable expires field
_MISSING = object()


# ── Time helpers ──────────────────────────────────────────────────────────────

def is_expired(expires_timestamp: str) -> bool:
    """Return True if the given ISO timestamp is in the past."""
    try:
        expires = datetime.fromisoformat(expires_timestamp)
    except (ValueError, TypeError):
        return False  # Unparseable → treat as not expired; log separately
    # Compare in a timezone-naive way (both local time)
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    return datetime.now() > expires


def time_until_expiry(expires_timestamp: str) -> float:
    """
    Return hours remaining until expiry (negative if already expired).
    Returns float('inf') if the timestamp cannot be parsed.
    """
    try:
        expires = datetime.fromisoformat(expires_timestamp)
    except (ValueError, TypeError):
        return float("inf")
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    delta = expires - datetime.now()
    return delta.total_seconds() / 3600


# ── Logging helpers ───────────────────────────────────────────────────────────

def _log(line: str) -> None:
    """Append a timestamped line to logs/approvals.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── File move helper ──────────────────────────────────────────────────────────

def _move(src: Path, dest_dir: Path) -> Path:
    """
    Move src into dest_dir.  Appends _1, _2 … on filename collision.
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


# ── Auto-rejection ────────────────────────────────────────────────────────────

def auto_reject_expired(approval_file: Path, vault_path: Path, dry_run: bool = False) -> bool:
    """
    Auto-reject a single expired approval file.

    Steps
    -----
    1. Parse frontmatter
    2. Update frontmatter: status, rejected_by, rejected_at, rejection_reason
    3. Append ## AUTO-REJECTION (TIMEOUT) section to file body
    4. Write the updated file back to disk
    5. Move from Pending_Approval/ to Rejected/
    6. Append two log lines to logs/approvals.log

    Parameters
    ----------
    approval_file : Path
        Full path to the file inside Pending_Approval/
    vault_path : Path
        Root vault directory
    dry_run : bool
        If True, print actions but do not modify or move any files

    Returns
    -------
    bool — True on success, False if an error occurred
    """
    rejected_dir = vault_path / "Rejected"
    now          = datetime.now()
    now_iso      = now.isoformat(timespec="seconds")
    now_display  = now.strftime("%Y-%m-%d %H:%M:%S")

    # ── 1. Parse frontmatter ──────────────────────────────────────────────────
    try:
        post = frontmatter.load(str(approval_file))
    except Exception as exc:
        print(f"[approval-checker] ERROR parsing {approval_file.name}: {exc}")
        return False

    action_type = post.get("action_type", "unknown")

    # ── 2. Update frontmatter ─────────────────────────────────────────────────
    post["status"]           = "rejected"
    post["rejected_by"]      = "system"
    post["rejected_at"]      = now_iso
    post["rejection_reason"] = TIMEOUT_REASON

    # ── 3. Build rejection section ────────────────────────────────────────────
    rejection_section = (
        "\n---\n\n"
        "## AUTO-REJECTION (TIMEOUT)\n\n"
        "**Rejected By:** System (Automatic)\n"
        f"**Rejected At:** {now_display}\n"
        f"**Reason:** Approval timeout — no decision within 24 hours\n\n"
        "**This approval expired and was automatically rejected for safety.**\n\n"
        "If this action is still needed:\n"
        "1. Review the original request\n"
        "2. Create a new approval request\n"
        "3. Ensure timely approval (within 24 hours)\n"
    )

    updated_content = frontmatter.dumps(post) + rejection_section

    # ── Dry-run gate ──────────────────────────────────────────────────────────
    if dry_run:
        hours_over = abs(time_until_expiry(str(post.get("expires", ""))))
        print(
            f"  [dry-run] Would auto-reject: {approval_file.name}"
            f"  (action_type={action_type}, {hours_over:.1f}h over limit)"
        )
        return True

    # ── 4. Write updated file ─────────────────────────────────────────────────
    try:
        approval_file.write_text(updated_content, encoding="utf-8")
    except Exception as exc:
        print(f"[approval-checker] ERROR writing {approval_file.name}: {exc}")
        return False

    # ── 5. Move to Rejected/ ──────────────────────────────────────────────────
    try:
        _move(approval_file, rejected_dir)
    except Exception as exc:
        print(f"[approval-checker] ERROR moving {approval_file.name}: {exc}")
        return False

    # ── 6. Log ────────────────────────────────────────────────────────────────
    _log(f"[{now_display}] AUTO_REJECTED | {approval_file.name} | Rejected by: system")
    _log(f"[{now_display}] REASON        | \"{TIMEOUT_REASON}\"")

    return True


# ── Dashboard update ──────────────────────────────────────────────────────────

def update_dashboard_timeouts(vault_path: Path, expired_count: int) -> None:
    """
    Reflect auto-rejections in Dashboard.md.

    - Decrement 'Pending approvals' by expired_count
    - Increment 'Actions rejected' by expired_count
    - Add a Recent Activity entry
    """
    if expired_count == 0:
        return

    try:
        update_stats(vault_path, "pending_approvals", -expired_count, operation="increment")
        update_stats(vault_path, "actions_rejected",   expired_count, operation="increment")

        noun = "approval" if expired_count == 1 else "approvals"
        update_activity(
            vault_path,
            f"approval-checker: auto-rejected {expired_count} expired {noun}",
        )
        update_component_status(vault_path, "Approval Checker", "online")
        print(f"[approval-checker] Dashboard updated: -{expired_count} pending, +{expired_count} rejected.")
    except Exception as exc:
        print(f"[approval-checker] WARNING: dashboard update failed: {exc}")


# ── Expiring-soon check ───────────────────────────────────────────────────────

def check_expiring_soon(vault_path: str | Path, warning_hours: float = 2.0) -> list[dict]:
    """
    Return a list of approval files that expire within ``warning_hours``.

    Each entry is a dict:
        file       (str)   — filename
        expires    (str)   — raw expires value from frontmatter
        hours_left (float) — hours remaining (always >= 0 here)

    Files that are already expired are excluded (handled by check_pending_approvals).
    """
    vault_path   = Path(vault_path)
    pending_dir  = vault_path / "Pending_Approval"
    expiring_soon: list[dict] = []

    if not pending_dir.exists():
        return expiring_soon

    for md_file in sorted(pending_dir.glob("*.md")):
        try:
            post = frontmatter.load(str(md_file))
        except Exception:
            continue

        expires_raw = post.get("expires", _MISSING)
        if expires_raw is _MISSING:
            continue

        hours_left = time_until_expiry(str(expires_raw))
        if 0 < hours_left <= warning_hours:
            expiring_soon.append({
                "file":       md_file.name,
                "expires":    str(expires_raw),
                "hours_left": round(hours_left, 2),
            })

    return sorted(expiring_soon, key=lambda d: d["hours_left"])


# ── Main function ─────────────────────────────────────────────────────────────

def check_pending_approvals(vault_path: str | Path, dry_run: bool = False) -> dict:
    """
    Check for expired approvals and auto-reject them.

    Parameters
    ----------
    vault_path : str | Path
        Root vault directory (must contain a Pending_Approval/ subfolder).
    dry_run : bool
        If True, report what would happen without moving or modifying files.

    Returns
    -------
    dict with keys:
        total_pending  (int)        — files found in Pending_Approval/
        expired_count  (int)        — files auto-rejected this run
        active_count   (int)        — files still within expiry window
        errors         (list[str])  — filenames that could not be processed
        expired_files  (list[str])  — filenames that were auto-rejected
        next_expiring  (dict|None)  — {"file": str, "hours": float} of the
                                      soonest-expiring active file, or None
    """
    vault_path  = Path(vault_path)
    pending_dir = vault_path / "Pending_Approval"

    summary: dict = {
        "total_pending": 0,
        "expired_count": 0,
        "active_count":  0,
        "errors":        [],
        "expired_files": [],
        "next_expiring": None,
    }

    # ── Ensure folder exists ──────────────────────────────────────────────────
    if not pending_dir.exists():
        pending_dir.mkdir(parents=True, exist_ok=True)
        print("[approval-checker] Pending_Approval/ folder not found — created empty folder.")
        return summary

    md_files = sorted(pending_dir.glob("*.md"))

    if not md_files:
        print("[approval-checker] No pending approvals found.")
        return summary

    summary["total_pending"] = len(md_files)
    now_display = _now_str()

    # ── Scan each file ────────────────────────────────────────────────────────
    active_files: list[tuple[str, float]] = []  # (filename, hours_left)

    for md_file in md_files:
        # Parse frontmatter
        try:
            post = frontmatter.load(str(md_file))
        except Exception as exc:
            print(f"[approval-checker] ERROR parsing {md_file.name}: {exc}")
            summary["errors"].append(md_file.name)
            continue

        expires_raw = post.get("expires", _MISSING)

        # Missing expires field — log a warning, skip auto-rejection
        if expires_raw is _MISSING:
            print(f"[approval-checker] WARNING: {md_file.name} has no 'expires' field — skipping")
            summary["active_count"] += 1
            continue

        hours_left = time_until_expiry(str(expires_raw))

        if is_expired(str(expires_raw)):
            # Auto-reject
            hours_over = abs(hours_left)
            print(f"[approval-checker] Expired ({hours_over:.1f}h over limit): {md_file.name}")
            ok = auto_reject_expired(md_file, vault_path, dry_run=dry_run)
            if ok:
                summary["expired_count"] += 1
                summary["expired_files"].append(md_file.name)
            else:
                summary["errors"].append(md_file.name)
        else:
            summary["active_count"] += 1
            active_files.append((md_file.name, hours_left))
            print(f"[approval-checker] Active  ({hours_left:.1f}h remaining):   {md_file.name}")

    # ── Determine next-expiring active file ───────────────────────────────────
    if active_files:
        active_files.sort(key=lambda t: t[1])
        next_name, next_hours = active_files[0]
        summary["next_expiring"] = {"file": next_name, "hours": round(next_hours, 2)}

    # ── Write scan summary to approvals.log ───────────────────────────────────
    if not dry_run:
        _log(
            f"[{now_display}] TIMEOUT_CHECK | "
            f"Scanned: {summary['total_pending']} pending | "
            f"Expired: {summary['expired_count']} | "
            f"Active: {summary['active_count']}"
        )

    # ── Update Dashboard ──────────────────────────────────────────────────────
    if not dry_run:
        update_dashboard_timeouts(vault_path, summary["expired_count"])

    return summary


# ── Summary printer ───────────────────────────────────────────────────────────

def _print_summary(result: dict, verbose: bool = False) -> None:
    sep = "=" * 50
    print(f"\n{sep}")
    print("APPROVAL TIMEOUT CHECK")
    print(sep)
    print(f"Total Pending : {result['total_pending']}")
    print(f"Expired       : {result['expired_count']}")
    print(f"Active        : {result['active_count']}")

    if result["errors"]:
        print(f"Errors        : {len(result['errors'])}")
        for name in result["errors"]:
            print(f"  - {name}")

    if verbose and result["expired_files"]:
        print("\nAuto-Rejected:")
        for name in result["expired_files"]:
            print(f"  - {name}")

    if result["next_expiring"]:
        nxt = result["next_expiring"]
        print(f"\nNext Expiring : {nxt['file']}  ({nxt['hours']:.1f}h remaining)")

    print(f"{sep}\n")


# ── Test helper ───────────────────────────────────────────────────────────────

def test_check_approvals(vault_path: str | Path | None = None) -> dict:
    """
    Quick smoke-test: run the checker against the default vault and print results.

    Parameters
    ----------
    vault_path : str | Path | None
        Override the vault location.  Defaults to DEFAULT_VAULT.

    Returns
    -------
    The summary dict from check_pending_approvals().
    """
    path = Path(vault_path) if vault_path else DEFAULT_VAULT
    print("Testing approval timeout checker…")
    result = check_pending_approvals(str(path))
    _print_summary(result, verbose=True)
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_approvals",
        description="Check Pending_Approval/ for expired files and auto-reject them.",
    )
    parser.add_argument(
        "--vault",
        default=str(DEFAULT_VAULT),
        help="Path to the vault root (default: AI_Employee_Vault)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be rejected without modifying or moving files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed output including per-file results",
    )
    parser.add_argument(
        "--warn-hours",
        type=float,
        default=0.0,
        metavar="HOURS",
        help="Also list approvals expiring within HOURS (0 = disabled, default)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run test_check_approvals() and exit",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.test:
        test_check_approvals(args.vault)
        return

    vault_path = Path(args.vault)

    if args.dry_run:
        print("[approval-checker] DRY-RUN mode — no files will be modified.\n")

    result = check_pending_approvals(str(vault_path), dry_run=args.dry_run)

    if args.verbose or args.dry_run:
        _print_summary(result, verbose=True)
    else:
        # Always print a one-liner when run non-verbosely (useful for cron logs)
        print(
            f"[approval-checker] Done — "
            f"scanned: {result['total_pending']}, "
            f"expired: {result['expired_count']}, "
            f"active: {result['active_count']}"
        )

    # ── Expiring-soon warning ─────────────────────────────────────────────────
    if args.warn_hours > 0:
        soon = check_expiring_soon(vault_path, warning_hours=args.warn_hours)
        if soon:
            print(f"\n[approval-checker] WARNING: {len(soon)} approval(s) expiring within {args.warn_hours}h:")
            for item in soon:
                print(f"  - {item['file']}  ({item['hours_left']:.1f}h left)")
        elif args.verbose:
            print(f"[approval-checker] No approvals expiring within {args.warn_hours}h.")

    if result["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
