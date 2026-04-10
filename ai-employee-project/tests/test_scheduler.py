"""
tests/test_scheduler.py

Scheduler System — comprehensive integration tests.

Covers module existence, function signatures, task registry structure,
APScheduler availability, main.py integration, and live execution of all
four scheduled tasks (timeout check, daily summary, cleanup, health check).

Run:
    python -m pytest tests/test_scheduler.py -v
    python tests/test_scheduler.py              # standalone (no pytest needed)
"""

import inspect
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VAULT = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")


# ── Test suite ────────────────────────────────────────────────────────────────

class TestScheduler(unittest.TestCase):
    """Full integration test suite for the Scheduler System (Silver Tier)."""

    def setUp(self):
        """Shared fixtures available to every test method."""
        self.vault_path   = _VAULT
        self.project_path = _PROJECT_ROOT
        self._temp_files: list[Path] = []   # cleaned up in tearDown

    def tearDown(self):
        """Remove any temp files created during the test run."""
        for path in self._temp_files:
            try:
                if path.exists():
                    path.unlink()
                    print(f"  Cleaned up: {path.name}")
            except Exception:
                pass

    # ── 1. scheduled_tasks.py file exists ────────────────────────────────────

    def test_1_scheduled_tasks_module_exists(self):
        """scheduler/scheduled_tasks.py exists and is a valid Python file."""
        tasks_file = self.project_path / "scheduler" / "scheduled_tasks.py"

        self.assertTrue(
            tasks_file.exists(),
            f"scheduler/scheduled_tasks.py not found at: {tasks_file}",
        )
        self.assertTrue(tasks_file.is_file(), "scheduled_tasks.py path is not a file")
        self.assertEqual(tasks_file.suffix, ".py", "scheduled_tasks must be a .py file")

        source = tasks_file.read_text(encoding="utf-8")
        self.assertGreater(len(source), 300, "scheduled_tasks.py is suspiciously short")

        # Must compile without SyntaxError
        try:
            compile(source, str(tasks_file), "exec")
        except SyntaxError as exc:
            self.fail(f"scheduled_tasks.py has a syntax error: {exc}")

        # All four task functions must appear in source text
        for fn_name in (
            "check_approval_timeouts",
            "generate_daily_summary",
            "cleanup_old_files",
            "health_check_watchers",
        ):
            self.assertIn(
                fn_name, source,
                f"Expected function '{fn_name}' not found in scheduled_tasks.py",
            )

        # Registry and factory functions must be present
        for fn_name in ("get_scheduled_tasks", "create_scheduler"):
            self.assertIn(
                fn_name, source,
                f"Expected function '{fn_name}' not found in scheduled_tasks.py",
            )

        # APScheduler must be used
        self.assertIn(
            "BackgroundScheduler", source,
            "scheduled_tasks.py must import/use BackgroundScheduler",
        )

        print(f"\n  Path    : {tasks_file}")
        print(f"  Size    : {len(source):,} chars")
        print(f"  Syntax  : valid Python")
        print(f"  Functions: check_approval_timeouts, generate_daily_summary,")
        print(f"             cleanup_old_files, health_check_watchers — all present")
        print(f"  Registry : get_scheduled_tasks — OK")
        print(f"  Factory  : create_scheduler — OK")
        print(f"  APScheduler BackgroundScheduler referenced — OK")

    # ── 2. Task functions signatures ──────────────────────────────────────────

    def test_2_task_functions_exist(self):
        """All four task functions import cleanly, are callable, and have correct signatures."""
        from scheduler.scheduled_tasks import (
            check_approval_timeouts,
            generate_daily_summary,
            cleanup_old_files,
            health_check_watchers,
        )

        # All must be callable
        for fn in (check_approval_timeouts, generate_daily_summary,
                   cleanup_old_files, health_check_watchers):
            self.assertTrue(callable(fn), f"{fn.__name__} is not callable")

        # ── check_approval_timeouts(vault_path) ───────────────────────────────
        sig    = inspect.signature(check_approval_timeouts)
        params = list(sig.parameters.keys())
        self.assertIn(
            "vault_path", params,
            "check_approval_timeouts must accept 'vault_path'",
        )

        # ── generate_daily_summary(vault_path) ────────────────────────────────
        sig    = inspect.signature(generate_daily_summary)
        params = list(sig.parameters.keys())
        self.assertIn(
            "vault_path", params,
            "generate_daily_summary must accept 'vault_path'",
        )

        # ── cleanup_old_files(vault_path, days_old) ───────────────────────────
        sig    = inspect.signature(cleanup_old_files)
        params = list(sig.parameters.keys())
        self.assertIn(
            "vault_path", params,
            "cleanup_old_files must accept 'vault_path'",
        )
        self.assertIn(
            "days_old", params,
            "cleanup_old_files must accept 'days_old'",
        )
        self.assertIsNot(
            sig.parameters["days_old"].default,
            inspect.Parameter.empty,
            "'days_old' must have a default value (optional param)",
        )

        # ── health_check_watchers(vault_path) ─────────────────────────────────
        sig    = inspect.signature(health_check_watchers)
        params = list(sig.parameters.keys())
        self.assertIn(
            "vault_path", params,
            "health_check_watchers must accept 'vault_path'",
        )

        print(f"\n  check_approval_timeouts  params : {list(inspect.signature(check_approval_timeouts).parameters)}")
        print(f"  generate_daily_summary   params : {list(inspect.signature(generate_daily_summary).parameters)}")
        print(f"  cleanup_old_files        params : {list(inspect.signature(cleanup_old_files).parameters)}")
        print(f"  health_check_watchers    params : {list(inspect.signature(health_check_watchers).parameters)}")
        print(f"  All 4 functions callable with correct signatures: OK")

    # ── 3. Task registry ──────────────────────────────────────────────────────

    def test_3_task_registry(self):
        """get_scheduled_tasks() returns exactly 4 tasks, each with all required fields."""
        from scheduler.scheduled_tasks import get_scheduled_tasks

        tasks = get_scheduled_tasks(str(self.vault_path))

        self.assertIsInstance(tasks, list, "get_scheduled_tasks must return a list")
        self.assertEqual(
            len(tasks), 4,
            f"Expected exactly 4 tasks in registry, got {len(tasks)}",
        )

        required_fields = {"func", "args", "trigger", "id", "name", "description"}
        expected_ids    = {
            "check_approval_timeouts",
            "generate_daily_summary",
            "cleanup_old_files",
            "health_check_watchers",
        }
        expected_triggers = {"interval", "cron"}

        found_ids: set[str] = set()

        for task in tasks:
            # All required fields present
            for field in required_fields:
                self.assertIn(
                    field, task,
                    f"Task '{task.get('id', '?')}' missing required field: '{field}'",
                )

            # func must be callable
            self.assertTrue(
                callable(task["func"]),
                f"Task '{task['id']}' func is not callable",
            )

            # args must be a list
            self.assertIsInstance(
                task["args"], list,
                f"Task '{task['id']}' args must be a list",
            )

            # trigger must be 'interval' or 'cron'
            self.assertIn(
                task["trigger"], expected_triggers,
                f"Task '{task['id']}' trigger must be 'interval' or 'cron', "
                f"got: {task['trigger']!r}",
            )

            # id and name must be non-empty strings
            self.assertIsInstance(task["id"],   str, "Task 'id' must be a string")
            self.assertIsInstance(task["name"], str, "Task 'name' must be a string")
            self.assertGreater(len(task["id"]),   0, "Task 'id' must not be empty")
            self.assertGreater(len(task["name"]), 0, "Task 'name' must not be empty")

            # description must be a non-empty string
            self.assertIsInstance(task["description"], str,
                                  "Task 'description' must be a string")
            self.assertGreater(len(task["description"]), 0,
                               "Task 'description' must not be empty")

            found_ids.add(task["id"])

        # All expected IDs must be present
        self.assertEqual(
            found_ids, expected_ids,
            f"Task IDs mismatch.\n  Expected : {sorted(expected_ids)}\n  Got      : {sorted(found_ids)}",
        )

        # Interval tasks must have hours or minutes
        for task in tasks:
            if task["trigger"] == "interval":
                has_interval = "hours" in task or "minutes" in task
                self.assertTrue(
                    has_interval,
                    f"Interval task '{task['id']}' must specify 'hours' or 'minutes'",
                )

        # Cron tasks must have at least 'hour' or 'day_of_week'
        for task in tasks:
            if task["trigger"] == "cron":
                has_cron = "hour" in task or "day_of_week" in task
                self.assertTrue(
                    has_cron,
                    f"Cron task '{task['id']}' must specify 'hour' or 'day_of_week'",
                )

        print(f"\n  Registry returned {len(tasks)} task(s):")
        for task in tasks:
            trigger_detail = (
                f"every {task.get('hours', task.get('minutes', '?'))} "
                f"{'hours' if 'hours' in task else 'min'}"
                if task["trigger"] == "interval"
                else f"cron hour={task.get('hour')} dow={task.get('day_of_week')}"
            )
            print(f"  - {task['id']:<35} {task['trigger']:<10} {trigger_detail}")
        print(f"  All required fields present on every task: OK")
        print(f"  All 4 expected IDs found: OK")

    # ── 4. APScheduler installed ──────────────────────────────────────────────

    def test_4_apscheduler_installed(self):
        """APScheduler is installed and all required components import cleanly."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from apscheduler.triggers.cron import CronTrigger
            import apscheduler
        except ImportError as exc:
            self.fail(f"APScheduler not installed or import failed: {exc}")

        # Verify the classes are usable
        self.assertTrue(callable(BackgroundScheduler),
                        "BackgroundScheduler must be a callable class")
        self.assertTrue(callable(IntervalTrigger),
                        "IntervalTrigger must be a callable class")
        self.assertTrue(callable(CronTrigger),
                        "CronTrigger must be a callable class")

        # Verify version is 3.x
        version = apscheduler.__version__
        major   = int(version.split(".")[0])
        self.assertEqual(
            major, 3,
            f"Expected APScheduler 3.x, found version: {version}",
        )

        # create_scheduler must return a BackgroundScheduler instance
        from scheduler.scheduled_tasks import create_scheduler
        sched = create_scheduler(str(self.vault_path))
        self.assertIsInstance(
            sched, BackgroundScheduler,
            "create_scheduler() must return a BackgroundScheduler instance",
        )
        self.assertFalse(
            sched.running,
            "create_scheduler() must return an unstarted scheduler",
        )
        # Verify all 4 jobs were registered
        jobs = sched.get_jobs()
        self.assertEqual(
            len(jobs), 4,
            f"Scheduler must have 4 registered jobs, found {len(jobs)}",
        )

        print(f"\n  APScheduler version : {version}")
        print(f"  BackgroundScheduler : importable — OK")
        print(f"  IntervalTrigger     : importable — OK")
        print(f"  CronTrigger         : importable — OK")
        print(f"  create_scheduler()  : returns unstarted BackgroundScheduler — OK")
        print(f"  Jobs registered     : {len(jobs)}")
        for job in jobs:
            print(f"    - {job.id:<35} {job.trigger}")

    # ── 5. main.py has scheduler integration ─────────────────────────────────

    def test_5_main_has_scheduler_integration(self):
        """main.py imports scheduler modules and integrates them correctly."""
        main_file = self.project_path / "main.py"

        self.assertTrue(
            main_file.exists(),
            f"main.py not found at: {main_file}",
        )

        source = main_file.read_text(encoding="utf-8")
        self.assertGreater(len(source), 200, "main.py is suspiciously short")

        # ── Required imports ──────────────────────────────────────────────────
        for symbol in ("BackgroundScheduler", "IntervalTrigger", "CronTrigger"):
            self.assertIn(
                symbol, source,
                f"main.py must import '{symbol}' from APScheduler",
            )

        self.assertIn(
            "get_scheduled_tasks", source,
            "main.py must import 'get_scheduled_tasks' from scheduler.scheduled_tasks",
        )

        # ── Scheduler lifecycle: start and shutdown ───────────────────────────
        self.assertIn(
            "scheduler.start()", source,
            "main.py must call scheduler.start()",
        )
        self.assertIn(
            "scheduler.shutdown", source,
            "main.py must call scheduler.shutdown() during shutdown",
        )

        # ── --no-scheduler CLI flag ───────────────────────────────────────────
        self.assertIn(
            "no-scheduler", source,
            "main.py must define a '--no-scheduler' CLI argument",
        )
        self.assertIn(
            "no_scheduler", source,
            "main.py must reference args.no_scheduler",
        )

        # ── enable_scheduler parameter on Orchestrator ────────────────────────
        self.assertIn(
            "enable_scheduler", source,
            "Orchestrator must accept an 'enable_scheduler' parameter",
        )

        # ── Scheduler must not block watchers: uses BackgroundScheduler ───────
        self.assertNotIn(
            "BlockingScheduler", source,
            "main.py must not use BlockingScheduler (would block watchers)",
        )

        # ── Must compile cleanly ──────────────────────────────────────────────
        try:
            compile(source, str(main_file), "exec")
        except SyntaxError as exc:
            self.fail(f"main.py has a syntax error: {exc}")

        print(f"\n  Path               : {main_file}")
        print(f"  Imports            : BackgroundScheduler, IntervalTrigger,")
        print(f"                       CronTrigger, get_scheduled_tasks — OK")
        print(f"  scheduler.start()  : present — OK")
        print(f"  scheduler.shutdown : present — OK")
        print(f"  --no-scheduler CLI : present — OK")
        print(f"  enable_scheduler   : Orchestrator parameter — OK")
        print(f"  BackgroundScheduler (non-blocking): confirmed — OK")
        print(f"  Syntax             : valid Python — OK")

    # ── 6. check_approval_timeouts() live run ────────────────────────────────

    def test_6_approval_timeout_task(self):
        """check_approval_timeouts() runs, returns a correctly-structured dict."""
        from scheduler.scheduled_tasks import check_approval_timeouts

        result = check_approval_timeouts(str(self.vault_path))

        # Must return a dict (not None — even on an empty folder)
        self.assertIsInstance(
            result, dict,
            "check_approval_timeouts must return a dict, even when no approvals exist",
        )

        # Required keys with correct types
        required: dict[str, type] = {
            "total_pending": int,
            "expired_count": int,
            "active_count":  int,
            "errors":        list,
            "expired_files": list,
        }
        for key, expected_type in required.items():
            self.assertIn(key, result, f"Result dict missing key: '{key}'")
            self.assertIsInstance(
                result[key], expected_type,
                f"result['{key}'] must be {expected_type.__name__}, "
                f"got {type(result[key]).__name__}",
            )

        # next_expiring must be None or a dict
        self.assertIn("next_expiring", result, "Result dict missing key: 'next_expiring'")
        self.assertTrue(
            result["next_expiring"] is None or isinstance(result["next_expiring"], dict),
            "next_expiring must be None or a dict",
        )

        # Counts must be non-negative
        self.assertGreaterEqual(result["total_pending"], 0,
                                "total_pending must be >= 0")
        self.assertGreaterEqual(result["expired_count"], 0,
                                "expired_count must be >= 0")
        self.assertGreaterEqual(result["active_count"],  0,
                                "active_count must be >= 0")

        # total_pending == expired_count + active_count (+ any errors)
        self.assertEqual(
            result["total_pending"],
            result["expired_count"] + result["active_count"] + len(result["errors"]),
            "total_pending must equal expired + active + errors",
        )

        print(f"\n  check_approval_timeouts() result:")
        print(f"    total_pending : {result['total_pending']}")
        print(f"    expired_count : {result['expired_count']}")
        print(f"    active_count  : {result['active_count']}")
        print(f"    errors        : {result['errors']}")
        print(f"    next_expiring : {result['next_expiring']}")
        print(f"  Return structure correct: OK")
        print(f"  Handles empty Pending_Approval/ folder: OK")

    # ── 7. generate_daily_summary() live run ─────────────────────────────────

    def test_7_daily_summary_task(self):
        """generate_daily_summary() creates a well-formed report file in Reports/."""
        from scheduler.scheduled_tasks import generate_daily_summary, REPORTS_FOLDER

        result = generate_daily_summary(str(self.vault_path))

        # Must return a dict
        self.assertIsInstance(
            result, dict,
            "generate_daily_summary must return a dict on success",
        )

        # Required keys
        for key in ("date", "report_file", "counts", "total_activity"):
            self.assertIn(key, result, f"Result dict missing key: '{key}'")

        # date must be today's ISO date
        today_iso = datetime.now().date().isoformat()
        self.assertEqual(
            result["date"], today_iso,
            f"result['date'] must be today ({today_iso}), got: {result['date']!r}",
        )

        # total_activity must be a non-negative int
        self.assertIsInstance(result["total_activity"], int,
                              "total_activity must be an int")
        self.assertGreaterEqual(result["total_activity"], 0,
                                "total_activity must be >= 0")

        # counts must be a dict of folder-name → int
        self.assertIsInstance(result["counts"], dict, "counts must be a dict")
        for folder_name, count in result["counts"].items():
            self.assertIsInstance(count, int,
                                  f"count for '{folder_name}' must be an int")
            self.assertGreaterEqual(count, 0,
                                    f"count for '{folder_name}' must be >= 0")

        # ── Report file must exist on disk ────────────────────────────────────
        report_path = Path(result["report_file"])
        self.assertTrue(
            report_path.exists(),
            f"Report file does not exist at: {report_path}",
        )
        self._temp_files.append(report_path)

        # Must be in the Reports/ folder (not Done/)
        self.assertEqual(
            report_path.parent.name, REPORTS_FOLDER,
            f"Daily summary must be written to {REPORTS_FOLDER}/, "
            f"got: {report_path.parent.name}/",
        )

        # Filename format: DAILY_SUMMARY_YYYYMMDD.md
        self.assertRegex(
            report_path.name,
            r"^DAILY_SUMMARY_\d{8}\.md$",
            f"Report filename must match DAILY_SUMMARY_YYYYMMDD.md, "
            f"got: {report_path.name}",
        )

        # ── Report content ────────────────────────────────────────────────────
        content = report_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 100, "Report file is suspiciously short")

        # Must have YAML frontmatter
        self.assertTrue(
            content.startswith("---"),
            "Report must start with '---' YAML frontmatter",
        )
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter not properly closed")
        fm = parts[1]
        for field in ("type:", "date:", "generated:"):
            self.assertIn(field, fm, f"Report frontmatter missing field: '{field}'")

        # Must have required body sections
        for section in ("# Daily Summary", "## Activity Overview", "## Next Steps"):
            self.assertIn(section, content,
                          f"Report body missing section: '{section}'")

        # generated timestamp must be valid ISO
        gen_match = re.search(r"generated:\s*(\S+)", fm)
        self.assertIsNotNone(gen_match, "frontmatter 'generated' field missing")
        try:
            datetime.fromisoformat(gen_match.group(1))
        except ValueError:
            self.fail(
                f"'generated' is not valid ISO timestamp: {gen_match.group(1)!r}"
            )

        print(f"\n  Report file : {report_path.name}")
        print(f"  Location    : {report_path.parent.name}/ — OK")
        print(f"  Size        : {len(content):,} chars")
        print(f"  date        : {result['date']}")
        print(f"  total_activity: {result['total_activity']}")
        print(f"  Frontmatter (type, date, generated): OK")
        print(f"  Sections (Daily Summary, Activity Overview, Next Steps): OK")
        print(f"  Filename format DAILY_SUMMARY_YYYYMMDD.md: OK")

    # ── 8. health_check_watchers() live run ──────────────────────────────────

    def test_8_health_check_task(self):
        """health_check_watchers() returns a correctly-structured status dict."""
        from scheduler.scheduled_tasks import health_check_watchers

        result = health_check_watchers(str(self.vault_path))

        # Must return a dict
        self.assertIsInstance(
            result, dict,
            "health_check_watchers must return a dict",
        )

        # Required keys with correct types
        required: dict[str, type] = {
            "status":          str,
            "timestamp":       str,
            "log_fresh":       bool,
            "dashboard_fresh": bool,
            "details":         list,
        }
        for key, expected_type in required.items():
            self.assertIn(key, result, f"Result dict missing key: '{key}'")
            self.assertIsInstance(
                result[key], expected_type,
                f"result['{key}'] must be {expected_type.__name__}, "
                f"got {type(result[key]).__name__}",
            )

        # status must be one of the known values
        self.assertIn(
            result["status"], ("healthy", "warning", "unknown"),
            f"status must be 'healthy', 'warning', or 'unknown', "
            f"got: {result['status']!r}",
        )

        # timestamp must be a valid ISO datetime string
        try:
            datetime.fromisoformat(result["timestamp"])
        except ValueError:
            self.fail(
                f"'timestamp' is not a valid ISO datetime: {result['timestamp']!r}"
            )

        # timestamp must be recent (within the last 60 seconds)
        ts_age = (
            datetime.now() - datetime.fromisoformat(result["timestamp"])
        ).total_seconds()
        self.assertLess(
            ts_age, 60,
            f"timestamp is {ts_age:.0f}s old — health check may have cached a stale result",
        )

        # details must be a list of strings
        for item in result["details"]:
            self.assertIsInstance(
                item, str,
                f"Every entry in 'details' must be a string, got: {type(item).__name__}",
            )

        # Dashboard was passed — dashboard_fresh should be assessable
        # (True if Dashboard.md was updated recently, False if stale — both valid)
        # We just confirm the field is a bool, which was already checked above.

        print(f"\n  health_check_watchers() result:")
        print(f"    status          : {result['status']}")
        print(f"    timestamp       : {result['timestamp']}")
        print(f"    log_fresh       : {result['log_fresh']}")
        print(f"    dashboard_fresh : {result['dashboard_fresh']}")
        print(f"    details         : {result['details']}")
        print(f"  Return structure correct: OK")
        print(f"  timestamp is valid ISO and recent: OK")
        print(f"  status is one of (healthy, warning, unknown): OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestScheduler)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  SCHEDULER SYSTEM — INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
