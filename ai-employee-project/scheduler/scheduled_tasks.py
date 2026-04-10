"""
scheduler/scheduled_tasks.py

Defines and wires all APScheduler background tasks for the Silver Tier AI Employee.

Four tasks are registered:
  check_approval_timeouts  — every 1 hour
  generate_daily_summary   — every day at 18:00
  cleanup_old_files        — every Sunday at 00:00
  health_check_watchers    — every 30 minutes

Usage
-----
Standalone (runs scheduler until CTRL+C):
    python scheduler/scheduled_tasks.py
    python scheduler/scheduled_tasks.py --vault /path/to/vault
    python scheduler/scheduled_tasks.py --test

Embedded in main.py / Orchestrator:
    from scheduler.scheduled_tasks import create_scheduler

    scheduler = create_scheduler(vault_path)
    scheduler.start()          # non-blocking (BackgroundScheduler)
    ...
    scheduler.shutdown(wait=False)

APScheduler version: 3.x  (apscheduler>=3.10.0)
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from helpers.dashboard_updater import update_activity, update_component_status

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

LOG_DIR  = _PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "main.log"

# Files older than this are eligible for archival
CLEANUP_DAYS_DEFAULT = 90

# Daily summary is written here inside the vault
REPORTS_FOLDER = "Reports"

# Watcher log staleness threshold: if main.log hasn't been written within
# this many minutes we treat the watchers as potentially unhealthy.
STALE_LOG_MINUTES = 10

# ── Logging ───────────────────────────────────────────────────────────────────

logger = logging.getLogger("scheduler")


# ── Task 1: Check Approval Timeouts (hourly) ──────────────────────────────────

def check_approval_timeouts(vault_path: str) -> dict | None:
    """
    Scan Pending_Approval/ for expired files and auto-reject them.

    Schedule: every 1 hour
    Calls:    scheduler.check_approvals.check_pending_approvals()

    Returns the summary dict from check_pending_approvals, or None on error.
    """
    logger.info("Task: check_approval_timeouts — starting")

    try:
        from scheduler.check_approvals import check_pending_approvals

        result = check_pending_approvals(vault_path, dry_run=False)

        if result["expired_count"] > 0:
            noun = "approval" if result["expired_count"] == 1 else "approvals"
            logger.warning(
                f"Auto-rejected {result['expired_count']} expired {noun}. "
                f"Active remaining: {result['active_count']}"
            )
        else:
            logger.info(
                f"No expired approvals. "
                f"Active: {result['active_count']}, "
                f"Pending: {result['total_pending']}"
            )

        if result["next_expiring"]:
            nxt = result["next_expiring"]
            logger.info(
                f"Next expiring: {nxt['file']}  "
                f"({nxt['hours']:.1f}h remaining)"
            )

        logger.info("Task: check_approval_timeouts — done")
        return result

    except Exception as exc:
        logger.error(f"Task: check_approval_timeouts — FAILED: {exc}", exc_info=True)
        return None


# ── Task 2: Generate Daily Summary (daily at 18:00) ──────────────────────────

def generate_daily_summary(vault_path: str) -> dict | None:
    """
    Count today's activity across all vault folders and write a summary report.

    Schedule: every day at 18:00 (6 PM)
    Output:   AI_Employee_Vault/Reports/DAILY_SUMMARY_YYYYMMDD.md

    Returns a summary dict, or None on error.
    """
    logger.info("Task: generate_daily_summary — starting")

    try:
        vault = Path(vault_path)
        today = datetime.now().date()

        # ── Count files touched today in every vault folder ───────────────────
        watch_folders: dict[str, Path] = {
            "Inbox":            vault / "Inbox",
            "Needs_Action":     vault / "Needs_Action",
            "Plans":            vault / "Plans",
            "Pending_Approval": vault / "Pending_Approval",
            "Approved":         vault / "Approved",
            "Rejected":         vault / "Rejected",
            "Done":             vault / "Done",
        }

        counts: dict[str, int] = {}
        for name, folder in watch_folders.items():
            if folder.exists():
                counts[name] = sum(
                    1 for f in folder.glob("*.md")
                    if datetime.fromtimestamp(f.stat().st_mtime).date() == today
                )
            else:
                counts[name] = 0

        total_activity = sum(counts.values())

        # ── Build report content ──────────────────────────────────────────────
        generated_ts = datetime.now().isoformat(timespec="seconds")
        header_date  = today.strftime("%B %d, %Y")          # e.g. April 09, 2026
        date_slug    = today.strftime("%Y%m%d")

        content = (
            "---\n"
            "type: daily_summary\n"
            f"date: {today.isoformat()}\n"
            f"generated: {generated_ts}\n"
            "---\n\n"
            f"# Daily Summary — {header_date}\n\n"
            "## Activity Overview\n\n"
            "**New/Modified Items Today:**\n\n"
            f"| Folder            | Count |\n"
            f"|-------------------|-------|\n"
            f"| Inbox             | {counts.get('Inbox', 0):>5} |\n"
            f"| Needs Action      | {counts.get('Needs_Action', 0):>5} |\n"
            f"| Plans Created     | {counts.get('Plans', 0):>5} |\n"
            f"| Pending Approval  | {counts.get('Pending_Approval', 0):>5} |\n"
            f"| Approved          | {counts.get('Approved', 0):>5} |\n"
            f"| Rejected          | {counts.get('Rejected', 0):>5} |\n"
            f"| Completed (Done)  | {counts.get('Done', 0):>5} |\n\n"
            f"**Total Activity Today:** {total_activity} item(s)\n\n"
            "## Next Steps\n\n"
            "- Review `Needs_Action/` for pending tasks\n"
            "- Check `Pending_Approval/` for items awaiting decision\n"
            "- Follow up on any rejected actions in `Rejected/`\n\n"
            "---\n"
            f"*Generated automatically by AI Employee at {generated_ts}*\n"
        )

        # ── Write report file ─────────────────────────────────────────────────
        reports_dir = vault / REPORTS_FOLDER
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / f"DAILY_SUMMARY_{date_slug}.md"

        # Overwrite if already exists (re-generated later in the day)
        report_path.write_text(content, encoding="utf-8")

        # ── Dashboard activity entry ──────────────────────────────────────────
        try:
            update_activity(
                vault,
                f"Daily summary generated: {total_activity} item(s) today — "
                f"{report_path.name}",
            )
        except Exception as dash_exc:
            logger.warning(f"Dashboard update failed: {dash_exc}")

        logger.info(f"Daily summary written: {report_path}")
        logger.info(f"Task: generate_daily_summary — done  (total activity: {total_activity})")

        summary = {
            "date":           today.isoformat(),
            "report_file":    str(report_path),
            "counts":         counts,
            "total_activity": total_activity,
        }
        return summary

    except Exception as exc:
        logger.error(f"Task: generate_daily_summary — FAILED: {exc}", exc_info=True)
        return None


# ── Task 3: Cleanup Old Files (weekly, Sunday 00:00) ─────────────────────────

def cleanup_old_files(vault_path: str, days_old: int = CLEANUP_DAYS_DEFAULT) -> int:
    """
    Move files older than ``days_old`` days from Done/ and Rejected/ into
    AI_Employee_Vault/Archive/<folder>/.

    Schedule: every Sunday at 00:00 (midnight)

    Files are moved (not deleted) so the audit trail is preserved.
    Returns the number of files archived.
    """
    logger.info(f"Task: cleanup_old_files — starting (threshold: {days_old} days)")

    try:
        vault      = Path(vault_path)
        cutoff     = datetime.now() - timedelta(days=days_old)
        total      = 0
        per_folder: dict[str, int] = {}

        cleanup_targets: dict[str, Path] = {
            "Done":     vault / "Done",
            "Rejected": vault / "Rejected",
        }

        for folder_name, src_dir in cleanup_targets.items():
            if not src_dir.exists():
                per_folder[folder_name] = 0
                continue

            archive_dir = vault / "Archive" / folder_name
            archive_dir.mkdir(parents=True, exist_ok=True)

            old_files = [
                f for f in src_dir.glob("*.md")
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff
                # Never archive daily summary reports
                and not f.name.startswith("DAILY_SUMMARY_")
            ]

            for src_file in old_files:
                dest = archive_dir / src_file.name
                # Collision guard: append _1, _2 … if needed
                if dest.exists():
                    stem, suffix = src_file.stem, src_file.suffix
                    i = 1
                    while dest.exists():
                        dest = archive_dir / f"{stem}_{i}{suffix}"
                        i += 1
                src_file.rename(dest)
                logger.info(f"Archived: {folder_name}/{src_file.name} → Archive/{folder_name}/")
                total += 1

            per_folder[folder_name] = len(old_files)

        # ── Dashboard activity entry ──────────────────────────────────────────
        if total > 0:
            noun = "file" if total == 1 else "files"
            try:
                update_activity(
                    vault,
                    f"Weekly cleanup: archived {total} old {noun} "
                    f"(Done: {per_folder.get('Done', 0)}, "
                    f"Rejected: {per_folder.get('Rejected', 0)})",
                )
            except Exception as dash_exc:
                logger.warning(f"Dashboard update failed: {dash_exc}")

        logger.info(
            f"Task: cleanup_old_files — done  "
            f"(archived: {total}, "
            f"Done: {per_folder.get('Done', 0)}, "
            f"Rejected: {per_folder.get('Rejected', 0)})"
        )
        return total

    except Exception as exc:
        logger.error(f"Task: cleanup_old_files — FAILED: {exc}", exc_info=True)
        return 0


# ── Task 4: Health Check Watchers (every 30 minutes) ─────────────────────────

def health_check_watchers(vault_path: str | None = None) -> dict:
    """
    Check proxy indicators of watcher health.

    Schedule: every 30 minutes

    Since this module runs independently of the Orchestrator's thread list,
    health is assessed from observable side-effects:
      - Whether logs/main.log has been written within the last STALE_LOG_MINUTES
      - Whether AI_Employee_Vault/Dashboard.md has been updated recently

    When integrated into main.py, replace this function body with a direct
    call to Orchestrator._health_check() or pass live WatcherThread references.

    Returns a dict:
        status          ('healthy' | 'warning' | 'unknown')
        timestamp       ISO string
        log_fresh       bool  — main.log written within STALE_LOG_MINUTES
        dashboard_fresh bool  — Dashboard.md updated within last 15 minutes
        details         list[str]
    """
    logger.info("Task: health_check_watchers — starting")

    result: dict = {
        "status":          "unknown",
        "timestamp":       datetime.now().isoformat(timespec="seconds"),
        "log_fresh":       False,
        "dashboard_fresh": False,
        "details":         [],
    }

    issues: list[str] = []

    # ── Check main.log freshness ──────────────────────────────────────────────
    if LOG_FILE.exists():
        age_minutes = (
            datetime.now() - datetime.fromtimestamp(LOG_FILE.stat().st_mtime)
        ).total_seconds() / 60

        if age_minutes <= STALE_LOG_MINUTES:
            result["log_fresh"] = True
            result["details"].append(
                f"main.log updated {age_minutes:.1f}m ago — OK"
            )
        else:
            issues.append(
                f"main.log not updated for {age_minutes:.0f}m "
                f"(threshold: {STALE_LOG_MINUTES}m) — watchers may have stalled"
            )
    else:
        issues.append("main.log not found — orchestrator may not be running")

    # ── Check Dashboard.md freshness ─────────────────────────────────────────
    if vault_path:
        dashboard = Path(vault_path) / "Dashboard.md"
        if dashboard.exists():
            db_age_minutes = (
                datetime.now() - datetime.fromtimestamp(dashboard.stat().st_mtime)
            ).total_seconds() / 60

            if db_age_minutes <= 15:
                result["dashboard_fresh"] = True
                result["details"].append(
                    f"Dashboard.md updated {db_age_minutes:.1f}m ago — OK"
                )
            else:
                issues.append(
                    f"Dashboard.md not updated for {db_age_minutes:.0f}m "
                    f"— dashboard updater may have stalled"
                )
        else:
            issues.append("Dashboard.md not found in vault")

    # ── Derive overall status ─────────────────────────────────────────────────
    if not issues:
        result["status"] = "healthy"
        logger.info("Task: health_check_watchers — healthy")
    else:
        result["status"] = "warning"
        for issue in issues:
            logger.warning(f"Health: {issue}")
        result["details"].extend(issues)

    result["details"] = sorted(result["details"])
    logger.info("Task: health_check_watchers — done")
    return result


# ── Task registry ─────────────────────────────────────────────────────────────

def get_scheduled_tasks(vault_path: str) -> list[dict]:
    """
    Return the canonical list of all scheduled tasks with their APScheduler configs.

    Each entry is a dict suitable for passing directly to
    ``scheduler.add_job(**entry)`` (after extracting non-APScheduler keys).

    Keys:
        func        — callable task function
        args        — positional argument list
        trigger     — 'interval' | 'cron'
        id          — unique job ID string
        name        — human-readable label (shown in scheduler logs)
        description — one-liner for documentation
        + trigger-specific kwargs (hours/minutes for interval; hour/minute/day_of_week for cron)
    """
    return [
        {
            "func":        check_approval_timeouts,
            "args":        [vault_path],
            "trigger":     "interval",
            "hours":       1,
            "id":          "check_approval_timeouts",
            "name":        "Check Approval Timeouts",
            "description": "Auto-reject expired pending approvals (runs every hour)",
        },
        {
            "func":        generate_daily_summary,
            "args":        [vault_path],
            "trigger":     "cron",
            "hour":        18,
            "minute":      0,
            "id":          "generate_daily_summary",
            "name":        "Generate Daily Summary",
            "description": "Write daily activity report to Reports/ (runs daily at 18:00)",
        },
        {
            "func":        cleanup_old_files,
            "args":        [vault_path, CLEANUP_DAYS_DEFAULT],
            "trigger":     "cron",
            "day_of_week": "sun",
            "hour":        0,
            "minute":      0,
            "id":          "cleanup_old_files",
            "name":        "Cleanup Old Files",
            "description": (
                f"Archive Done/Rejected files older than {CLEANUP_DAYS_DEFAULT} days "
                "(runs weekly, Sunday 00:00)"
            ),
        },
        {
            "func":        health_check_watchers,
            "args":        [vault_path],
            "trigger":     "interval",
            "minutes":     30,
            "id":          "health_check_watchers",
            "name":        "Health Check",
            "description": "Check watcher health via log/dashboard freshness (runs every 30 min)",
        },
    ]


# ── Scheduler factory ─────────────────────────────────────────────────────────

# Module-level scheduler instance — created by create_scheduler(), stopped by
# stop_scheduler().  Kept at module level so standalone __main__ and embedding
# callers share a single instance.
_scheduler: BackgroundScheduler | None = None

# Keys in the task-registry dict that are NOT APScheduler add_job() kwargs
_REGISTRY_ONLY_KEYS = {"description"}


def create_scheduler(vault_path: str | Path) -> BackgroundScheduler:
    """
    Create and configure a BackgroundScheduler with all four registered tasks.

    Does NOT call scheduler.start() — call that yourself after
    ``create_scheduler()`` returns, so you can set up signal handlers first.

    Parameters
    ----------
    vault_path : str | Path
        Root vault directory.  Passed to every task as its first argument.

    Returns
    -------
    Configured (but not yet started) BackgroundScheduler instance.
    """
    global _scheduler

    vault_path = str(vault_path)

    sched = BackgroundScheduler(
        job_defaults={
            "coalesce":           True,   # merge missed firings into one
            "max_instances":      1,      # never run two copies of the same task
            "misfire_grace_time": 60,     # fire up to 60s late before skipping
        },
        # timezone omitted — APScheduler falls back to tzlocal.get_localzone()
    )

    for task in get_scheduled_tasks(vault_path):
        # Strip keys that belong to the registry but not to APScheduler
        job_kwargs = {k: v for k, v in task.items() if k not in _REGISTRY_ONLY_KEYS}
        sched.add_job(**job_kwargs)
        logger.info(
            f"Registered job: {task['id']!r:35s}  "
            f"trigger={task['trigger']}"
        )

    _scheduler = sched
    return sched


def stop_scheduler(wait: bool = False) -> None:
    """
    Shut down the module-level scheduler if it is running.

    Parameters
    ----------
    wait : bool
        If True, block until all currently-running jobs complete before stopping.
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=wait)
        logger.info("Scheduler shut down.")
    _scheduler = None


# ── Status printer ────────────────────────────────────────────────────────────

def print_scheduler_status(vault_path: str | None = None) -> None:
    """Print a human-readable table of all registered tasks and their next run times."""
    sched = _scheduler
    if sched is None or not sched.running:
        print("[scheduler] Scheduler is not running.")
        return

    jobs = sched.get_jobs()
    sep  = "-" * 70
    print(f"\n{sep}")
    print(f"  {'JOB ID':<35} {'NEXT RUN':<22} TRIGGER")
    print(sep)
    for job in jobs:
        next_run = (
            job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            if job.next_run_time else "paused"
        )
        print(f"  {job.id:<35} {next_run:<22} {job.trigger}")
    print(f"{sep}\n")


# ── Test helper ───────────────────────────────────────────────────────────────

def test_scheduled_tasks(vault_path: str | Path | None = None) -> None:
    """
    Synchronously run all four tasks once and print results.
    Useful for verifying task logic without waiting for the scheduler to fire.

    Parameters
    ----------
    vault_path : str | Path | None
        Override the vault location.  Defaults to DEFAULT_VAULT.
    """
    path = str(vault_path) if vault_path else str(DEFAULT_VAULT)

    sep = "=" * 50
    print(f"\n{sep}")
    print("  SCHEDULED TASKS — TEST RUN")
    print(f"{sep}\n")

    # ── Task 1 ────────────────────────────────────────────────────────────────
    print("1. check_approval_timeouts")
    result = check_approval_timeouts(path)
    if result:
        print(
            f"   total_pending={result['total_pending']}  "
            f"expired={result['expired_count']}  "
            f"active={result['active_count']}"
        )
    else:
        print("   Result: None (error — check logs)")

    # ── Task 2 ────────────────────────────────────────────────────────────────
    print("\n2. generate_daily_summary")
    result = generate_daily_summary(path)
    if result:
        print(f"   Report: {Path(result['report_file']).name}")
        print(f"   Total activity today: {result['total_activity']}")
        for folder, count in result["counts"].items():
            if count:
                print(f"     {folder}: {count}")
    else:
        print("   Result: None (error — check logs)")

    # ── Task 3 ────────────────────────────────────────────────────────────────
    print("\n3. cleanup_old_files (dry-safe: threshold=365 days)")
    result = cleanup_old_files(path, days_old=365)
    print(f"   Files archived: {result}")

    # ── Task 4 ────────────────────────────────────────────────────────────────
    print("\n4. health_check_watchers")
    result = health_check_watchers(path)
    print(f"   Status: {result['status']}")
    for detail in result["details"]:
        print(f"   - {detail}")

    print(f"\n{sep}")
    print("  All tasks complete.")
    print(f"{sep}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scheduled_tasks",
        description="Run the AI Employee scheduled task engine.",
    )
    parser.add_argument(
        "--vault",
        default=str(DEFAULT_VAULT),
        help="Path to the vault root (default: AI_Employee_Vault)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run all tasks once synchronously and exit (no scheduler loop)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print scheduled job table once, then exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser


def _setup_logging(level_name: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, level_name.upper(), logging.INFO)
    fmt   = logging.Formatter(
        "[%(asctime)s] [%(name)-18s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler    = logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def main() -> None:
    import signal

    parser = _build_parser()
    args   = parser.parse_args()
    _setup_logging(args.log_level)

    vault_path = args.vault

    # ── Test mode: run once and exit ──────────────────────────────────────────
    if args.test:
        test_scheduled_tasks(vault_path)
        return

    # ── Create and start scheduler ────────────────────────────────────────────
    sched = create_scheduler(vault_path)
    sched.start()

    logger.info("Scheduler started.  Press CTRL+C to stop.")

    # ── Status mode: print job table and exit ─────────────────────────────────
    if args.status:
        print_scheduler_status(vault_path)
        stop_scheduler(wait=False)
        return

    print_scheduler_status(vault_path)

    try:
        update_activity(Path(vault_path), "Scheduler started — 4 tasks registered")
    except Exception:
        pass

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    def _handle_signal(sig, frame):
        print()
        logger.info(f"Signal {sig} received — shutting down scheduler...")
        stop_scheduler(wait=True)
        try:
            update_activity(Path(vault_path), "Scheduler shut down gracefully")
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── Block main thread ─────────────────────────────────────────────────────
    try:
        while True:
            time.sleep(60)
            logger.debug("Scheduler heartbeat — still running")
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler(wait=True)


if __name__ == "__main__":
    main()
