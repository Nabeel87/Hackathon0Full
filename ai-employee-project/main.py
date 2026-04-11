"""
main.py — AI Employee master orchestrator.

Runs FileWatcher, GmailWatcher, LinkedInWatcher, and WhatsAppWatcher
continuously in separate threads with automatic restart, health monitoring,
and graceful shutdown.  A BackgroundScheduler runs four automated tasks
alongside the watchers.

Usage
-----
    python main.py
    python main.py --vault-path ~/AI_Employee_Vault --file-interval 60
    python main.py --gmail-interval 120 --linkedin-interval 180
    python main.py --whatsapp-interval 60
    python main.py --no-scheduler
    python main.py --log-level DEBUG

NOTE — WhatsApp first-time setup
    WhatsApp Web requires a one-time QR code login before headless monitoring
    can start.  If WhatsAppWatcher fails on first run, execute:
        python watchers/whatsapp_watcher.py
    A browser window will open — scan the QR code with your phone.
    The session is saved to ~/.credentials/whatsapp_session/context.json and
    all subsequent runs are fully automatic.
"""

import argparse
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ── Project root on sys.path ─────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from watchers.file_watcher import FileWatcher
from watchers.gmail_watcher import GmailWatcher
from watchers.linkedin_watcher import LinkedInWatcher
from watchers.whatsapp_watcher import WhatsAppWatcher
from helpers.dashboard_updater import update_activity, update_component_status
from scheduler.scheduled_tasks import get_scheduled_tasks

# ── Constants ─────────────────────────────────────────────────────────────────

HEALTH_CHECK_INTERVAL = 300   # seconds between health-check log lines
RESTART_DELAY         = 10    # seconds to wait before restarting a crashed watcher
LOG_DIR               = _PROJECT_ROOT / "logs"
LOG_FILE              = LOG_DIR / "main.log"

# Keys in the task-registry dict that are not APScheduler add_job() kwargs
_REGISTRY_ONLY_KEYS = {"description"}

BANNER = """
+-------------------------------------------------------+
|          AI Employee - Silver Tier                    |
|          24/7 Autonomous Monitoring                   |
+-------------------------------------------------------+
|  Starting watchers...                                 |
|  [+] File Watcher      (60s  interval)                |
|  [+] Gmail Watcher     (120s interval)                |
|  [+] LinkedIn Watcher  (180s interval)                |
|  [+] WhatsApp Watcher  (60s  interval)                |
+-------------------------------------------------------+
|  Starting scheduled tasks...                          |
|  [+] Check Approval Timeouts  (every hour)            |
|  [+] Generate Daily Summary   (daily at 6 PM)         |
|  [+] Cleanup Old Files        (weekly, Sunday 00:00)  |
|  [+] Health Check             (every 30 minutes)      |
+-------------------------------------------------------+
|  Dashboard :  AI_Employee_Vault/Dashboard.md          |
|  Logs      :  logs/main.log                           |
|  Press CTRL+C to stop.                                |
+-------------------------------------------------------+
|  NOTE: WhatsApp requires first-time QR code login.    |
|  If it fails, run: python watchers/whatsapp_watcher.py|
+-------------------------------------------------------+
"""

BANNER_NO_SCHEDULER = """
+-------------------------------------------------------+
|          AI Employee - Silver Tier                    |
|          24/7 Autonomous Monitoring                   |
+-------------------------------------------------------+
|  Starting watchers...                                 |
|  [+] File Watcher      (60s  interval)                |
|  [+] Gmail Watcher     (120s interval)                |
|  [+] LinkedIn Watcher  (180s interval)                |
|  [+] WhatsApp Watcher  (60s  interval)                |
+-------------------------------------------------------+
|  Scheduler disabled (--no-scheduler)                  |
+-------------------------------------------------------+
|  Dashboard :  AI_Employee_Vault/Dashboard.md          |
|  Logs      :  logs/main.log                           |
|  Press CTRL+C to stop.                                |
+-------------------------------------------------------+
|  NOTE: WhatsApp requires first-time QR code login.    |
|  If it fails, run: python watchers/whatsapp_watcher.py|
+-------------------------------------------------------+
"""

# ── Logging setup ─────────────────────────────────────────────────────────────

def _setup_logging(log_level: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)
    fmt   = logging.Formatter(
        "[%(asctime)s] [%(name)-18s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler    = logging.FileHandler(LOG_FILE, encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Quiet APScheduler's own verbose logging unless DEBUG is requested
    if log_level.upper() != "DEBUG":
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

    return logging.getLogger("orchestrator")


# ── WatcherThread ─────────────────────────────────────────────────────────────

class WatcherThread:
    """
    Wraps a BaseWatcher subclass in a daemon thread.
    Automatically restarts the watcher if it crashes.
    """

    def __init__(self, name: str, watcher_cls, watcher_kwargs: dict):
        self.name           = name
        self.watcher_cls    = watcher_cls
        self.watcher_kwargs = watcher_kwargs
        self.logger         = logging.getLogger(f"orchestrator.{name}")
        self._thread: threading.Thread | None = None
        self._watcher       = None
        self._stop_event    = threading.Event()
        self.restart_count  = 0
        self.last_started: datetime | None = None
        self.last_error: str | None = None

    # ── Public interface ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the watcher thread."""
        self._stop_event.clear()
        self._spawn()

    def stop(self) -> None:
        """Signal the watcher and thread to stop."""
        self._stop_event.set()
        if self._watcher is not None:
            self._watcher.stop()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _spawn(self) -> None:
        self._thread = threading.Thread(
            target=self._run_loop,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        self.last_started = datetime.now()
        self.logger.info(f"{self.name} thread started (restart #{self.restart_count})")

    def _run_loop(self) -> None:
        """
        Own poll loop — replaces BaseWatcher.run() so we can inject
        dashboard updates after every cycle without modifying watcher classes.
        """
        try:
            self._watcher = self.watcher_cls(**self.watcher_kwargs)
        except Exception as exc:
            self.last_error = str(exc)
            self.logger.error(f"{self.name} init failed: {exc}", exc_info=True)
            return

        vault_path     = self._watcher.vault_path
        check_interval = self._watcher.check_interval

        self.logger.info(
            f"{self.name} polling every {check_interval}s  "
            f"vault={vault_path}"
        )

        while not self._stop_event.is_set():
            # ── one poll cycle ────────────────────────────────────────────────
            try:
                items = self._watcher.check_for_updates()
            except Exception as exc:
                self.last_error = str(exc)
                self.logger.error(
                    f"{self.name} check_for_updates failed: {exc}", exc_info=True
                )
                items = []

            created = []
            for item in items:
                try:
                    path = self._watcher.create_action_file(item)
                    created.append(path)
                    self.logger.info(f"Card created: {path.name}")
                except Exception as exc:
                    self.logger.error(
                        f"create_action_file failed: {exc}", exc_info=True
                    )

            # ── dashboard update after every cycle ────────────────────────────
            if created:
                self._update_dashboard(vault_path, len(created))

            # ── sleep in 1-second ticks ───────────────────────────────────────
            elapsed = 0
            while not self._stop_event.is_set() and elapsed < check_interval:
                self._stop_event.wait(timeout=1)
                elapsed += 1

        self.logger.info(f"{self.name} thread exiting.")

    def _update_dashboard(self, vault_path: Path, n: int) -> None:
        """Log activity + update stats + resync all vault counts on dashboard."""
        try:
            from helpers.dashboard_updater import update_stats, refresh_vault_counts
            component_map = {
                "FileWatcher":      ("File Monitor",           "files_monitored"),
                "GmailWatcher":     ("Gmail Monitor",          "emails_checked"),
                "LinkedInWatcher":  ("LinkedIn Monitor Skill", "linkedin_checked"),
                "WhatsAppWatcher":  ("WhatsApp Monitor",       "whatsapp_messages_checked"),
            }
            component, stat_key = component_map.get(self.name, (self.name, None))
            label = (
                "file(s)"         if self.name == "FileWatcher"      else
                "notification(s)" if self.name == "LinkedInWatcher"  else
                "message(s)"      if self.name == "WhatsAppWatcher"  else
                "email(s)"
            )
            activity = f"{component}: {n} new {label} detected"

            update_activity(vault_path, activity)
            update_component_status(vault_path, component, "online")
            if stat_key:
                update_stats(vault_path, stat_key, n, operation="increment")
            refresh_vault_counts(vault_path)

            self.logger.info(f"Dashboard updated: {activity}")
        except Exception as exc:
            self.logger.warning(f"Dashboard update failed: {exc}")


# ── Scheduler helpers ─────────────────────────────────────────────────────────

def _build_scheduler(vault_path: Path, logger: logging.Logger) -> BackgroundScheduler:
    """
    Create a BackgroundScheduler and register all tasks from get_scheduled_tasks().

    Uses coalesce=True and max_instances=1 so a slow task never piles up.
    Does NOT call scheduler.start() — that is the caller's responsibility.
    """
    sched = BackgroundScheduler(
        job_defaults={
            "coalesce":           True,
            "max_instances":      1,
            "misfire_grace_time": 60,
        },
    )

    tasks = get_scheduled_tasks(str(vault_path))

    for task in tasks:
        # Strip registry-only metadata keys before passing to APScheduler
        job_kwargs = {k: v for k, v in task.items() if k not in _REGISTRY_ONLY_KEYS}

        if task["trigger"] == "interval":
            trigger = IntervalTrigger(
                hours=task.get("hours", 0),
                minutes=task.get("minutes", 0),
            )
        else:  # cron
            trigger = CronTrigger(
                hour=task.get("hour"),
                minute=task.get("minute"),
                day_of_week=task.get("day_of_week"),
            )

        # Replace the 'trigger' string key with the concrete trigger object
        job_kwargs.pop("trigger")
        sched.add_job(trigger=trigger, replace_existing=True, **job_kwargs)

        logger.info(
            f"Scheduled: {task['name']:<30}  {task.get('description', '')}"
        )

    return sched


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Starts, monitors, and cleanly shuts down all watcher threads and the
    background task scheduler.
    """

    def __init__(
        self,
        vault_path: Path,
        file_interval: int,
        gmail_interval: int,
        linkedin_interval: int,
        whatsapp_interval: int,
        enable_scheduler: bool = True,
    ):
        self.vault_path       = vault_path
        self.enable_scheduler = enable_scheduler
        self.logger           = logging.getLogger("orchestrator")
        self._shutdown        = threading.Event()
        self._scheduler: BackgroundScheduler | None = None

        self._watchers: list[WatcherThread] = [
            WatcherThread(
                name="FileWatcher",
                watcher_cls=FileWatcher,
                watcher_kwargs={
                    "vault_path":     vault_path,
                    "check_interval": file_interval,
                },
            ),
            WatcherThread(
                name="GmailWatcher",
                watcher_cls=GmailWatcher,
                watcher_kwargs={
                    "vault_path":     vault_path,
                    "check_interval": gmail_interval,
                },
            ),
            WatcherThread(
                name="LinkedInWatcher",
                watcher_cls=LinkedInWatcher,
                watcher_kwargs={
                    "vault_path":     vault_path,
                    "check_interval": linkedin_interval,
                },
            ),
            WatcherThread(
                name="WhatsAppWatcher",
                watcher_cls=WhatsAppWatcher,
                watcher_kwargs={
                    "vault_path":     vault_path,
                    "check_interval": whatsapp_interval,
                },
            ),
        ]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.logger.info("Orchestrator starting...")
        update_activity(self.vault_path, "Orchestrator started — all watchers launching")

        # ── Start watcher threads ─────────────────────────────────────────────
        for wt in self._watchers:
            wt.start()
        self.logger.info(f"All {len(self._watchers)} watcher(s) started.")

        # ── Start background scheduler ────────────────────────────────────────
        if self.enable_scheduler:
            self.logger.info("Initializing task scheduler...")
            self._scheduler = _build_scheduler(self.vault_path, self.logger)
            self._scheduler.start()
            self.logger.info("Scheduler started successfully.")
            try:
                update_activity(
                    self.vault_path,
                    "Scheduler started — 4 automated tasks registered",
                )
            except Exception:
                pass
        else:
            self.logger.info("Scheduler disabled (--no-scheduler).")

        self._log_scheduled_tasks_info()
        self._main_loop()

    def shutdown(self) -> None:
        self.logger.info("Shutdown requested — stopping all components...")
        self._shutdown.set()

        # ── Stop scheduler first (non-blocking) ───────────────────────────────
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler stopped.")

        # ── Stop watcher threads ──────────────────────────────────────────────
        for wt in self._watchers:
            wt.stop()
            self.logger.info(f"  {wt.name} stopped.")

        try:
            update_activity(self.vault_path, "Orchestrator shut down gracefully")
        except Exception:
            pass

        self.logger.info("All components stopped. Goodbye.")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        """Block the main thread, running health checks and dashboard refreshes."""
        last_health    = time.monotonic()
        last_dashboard = time.monotonic()

        while not self._shutdown.is_set():
            now = time.monotonic()

            if now - last_dashboard >= 60:
                self._refresh_dashboard()
                last_dashboard = now

            if now - last_health >= HEALTH_CHECK_INTERVAL:
                self._health_check()
                last_health = now

            self._shutdown.wait(timeout=5)

    def _refresh_dashboard(self) -> None:
        """Sync vault folder counts and component statuses every 60s."""
        try:
            from helpers.dashboard_updater import refresh_vault_counts
            refresh_vault_counts(self.vault_path)
            self.logger.debug("Dashboard refreshed (60s tick).")
        except Exception as exc:
            self.logger.warning(f"Dashboard refresh failed: {exc}")

    # ── Health check ──────────────────────────────────────────────────────────

    def _health_check(self) -> None:
        self.logger.info("-- Health check -----------------------------------------------")
        all_ok = True

        # ── Watcher threads ───────────────────────────────────────────────────
        for wt in self._watchers:
            status   = "ALIVE" if wt.is_alive else "DEAD"
            restarts = wt.restart_count
            since    = wt.last_started.strftime("%H:%M:%S") if wt.last_started else "--"
            self.logger.info(
                f"  {wt.name:<15} {status:<6}  restarts={restarts}  "
                f"started={since}"
            )

            if not wt.is_alive and not self._shutdown.is_set():
                all_ok = False
                self.logger.warning(f"  {wt.name} is not alive — restarting...")
                wt.restart_count += 1
                wt.start()

        # ── Scheduler ─────────────────────────────────────────────────────────
        if self._scheduler is not None:
            sched_status = "RUNNING" if self._scheduler.running else "STOPPED"
            self.logger.info(f"  {'Scheduler':<15} {sched_status}")
            if not self._scheduler.running and not self._shutdown.is_set():
                all_ok = False
                self.logger.warning("  Scheduler stopped unexpectedly — restarting...")
                try:
                    self._scheduler.start()
                except Exception as exc:
                    self.logger.error(f"  Scheduler restart failed: {exc}")

        status_line = "All components healthy." if all_ok else "Restart(s) triggered."
        self.logger.info(f"  {status_line}")
        self.logger.info("---------------------------------------------------------------")

    # ── Startup info ──────────────────────────────────────────────────────────

    def _log_scheduled_tasks_info(self) -> None:
        """Log a summary of registered scheduled tasks after startup."""
        if not self.enable_scheduler or self._scheduler is None:
            self.logger.info("No scheduled tasks (scheduler disabled).")
            return

        self.logger.info("Scheduled tasks registered:")
        self.logger.info("  Task                           Trigger")
        self.logger.info("  ------------------------------ ---------------------------")
        for job in self._scheduler.get_jobs():
            self.logger.info(f"  {job.name:<30} {job.trigger}")

        self.logger.info("")
        self.logger.info("Available scheduled tasks:")
        self.logger.info("  - Approval timeout check : every hour")
        self.logger.info("  - Daily summary          : daily at 6 PM")
        self.logger.info("  - File cleanup           : weekly on Sunday midnight")
        self.logger.info("  - Health check           : every 30 minutes")
        self.logger.info("")
        self.logger.info("To disable scheduler: python main.py --no-scheduler")
        self.logger.info("")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main",
        description="AI Employee — 24/7 orchestrator for watchers and scheduled tasks.",
    )
    parser.add_argument(
        "--vault-path",
        default=str(Path(
            "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
        )),
        help="Path to the AI Employee Vault (default: AI_Employee_Vault)",
    )
    parser.add_argument(
        "--file-interval",
        type=int, default=60,
        help="FileWatcher poll interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--gmail-interval",
        type=int, default=120,
        help="GmailWatcher poll interval in seconds (default: 120)",
    )
    parser.add_argument(
        "--linkedin-interval",
        type=int, default=180,
        help="LinkedInWatcher poll interval in seconds (default: 180)",
    )
    parser.add_argument(
        "--whatsapp-interval",
        type=int, default=60,
        help="WhatsAppWatcher poll interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Run without the background task scheduler",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args   = _parse_args()
    logger = _setup_logging(args.log_level)

    banner = BANNER_NO_SCHEDULER if args.no_scheduler else BANNER
    print(banner)

    logger.info(f"Vault          : {args.vault_path}")
    logger.info(f"File poll      : every {args.file_interval}s")
    logger.info(f"Gmail poll     : every {args.gmail_interval}s")
    logger.info(f"LinkedIn poll  : every {args.linkedin_interval}s")
    logger.info(f"WhatsApp poll  : every {args.whatsapp_interval}s")
    logger.info(f"Scheduler      : {'disabled' if args.no_scheduler else 'enabled'}")
    logger.info(f"Log level    : {args.log_level}")
    logger.info(f"Log file     : {LOG_FILE}")
    logger.info("")

    orchestrator = Orchestrator(
        vault_path         = Path(args.vault_path),
        file_interval      = args.file_interval,
        gmail_interval     = args.gmail_interval,
        linkedin_interval  = args.linkedin_interval,
        whatsapp_interval  = args.whatsapp_interval,
        enable_scheduler   = not args.no_scheduler,
    )

    # ── Graceful shutdown on CTRL+C or SIGTERM ────────────────────────────────
    def _handle_signal(sig, frame):
        print()
        logger.info(f"Signal {sig} received — initiating graceful shutdown...")
        orchestrator.shutdown()
        logging.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        orchestrator.start()
    except KeyboardInterrupt:
        orchestrator.shutdown()


if __name__ == "__main__":
    main()
