"""
tests/test_approval.py

Approval Workflow — comprehensive integration tests.

Covers skill file structure, timeout checker module, vault folder layout,
approval file creation and format, expired-approval detection and auto-rejection,
and approval log writability.  No external APIs or credentials required.

Run:
    python -m pytest tests/test_approval.py -v
    python tests/test_approval.py              # standalone (no pytest needed)
"""

import inspect
import re
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VAULT = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")


# ── Test suite ────────────────────────────────────────────────────────────────

class TestApprovalWorkflow(unittest.TestCase):
    """Full integration test suite for the Approval Workflow (Silver Tier)."""

    def setUp(self):
        """Shared fixtures available to every test method."""
        self.vault_path   = _VAULT
        self.project_path = _PROJECT_ROOT
        self._temp_files: list[Path] = []   # cleaned up in tearDown

    def tearDown(self):
        """Remove any temp files created during the test run from all approval folders."""
        search_dirs = [
            self.vault_path / "Pending_Approval",
            self.vault_path / "Approved",
            self.vault_path / "Rejected",
            self.vault_path / "Done",
        ]
        for tracked in self._temp_files:
            for folder in search_dirs:
                candidate = folder / Path(tracked).name
                # Also handle collision-renamed copies (_1, _2 …)
                if candidate.exists():
                    try:
                        candidate.unlink()
                        print(f"  Cleaned up: {candidate}")
                    except Exception:
                        pass
                # Sweep for renamed variants
                stem, suffix = Path(tracked).stem, Path(tracked).suffix
                for variant in folder.glob(f"{stem}_*{suffix}"):
                    try:
                        variant.unlink()
                        print(f"  Cleaned up variant: {variant.name}")
                    except Exception:
                        pass

    # ── 1. approve-action skill ───────────────────────────────────────────────

    def test_1_approve_skill_exists(self):
        """approve-action SKILL.md exists, has valid frontmatter, and is pure Markdown."""
        skill_path = self.project_path / ".claude" / "skills" / "approve-action" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"approve-action SKILL.md not found at: {skill_path}",
        )
        self.assertTrue(skill_path.is_file(), "approve-action path is not a file")

        content = skill_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 500, "approve-action SKILL.md is suspiciously short")

        # ── Frontmatter ───────────────────────────────────────────────────────
        self.assertTrue(content.startswith("---"), "SKILL.md must start with '---' frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter block not properly closed with '---'")

        fm = parts[1]

        for field in ("name:", "description:", "triggers:", "tier:"):
            self.assertIn(field, fm, f"approve-action frontmatter missing field: '{field}'")

        self.assertIn("approve-action", fm, "Frontmatter 'name' must be 'approve-action'")
        self.assertIn("silver", fm.lower(), "Frontmatter 'tier' must be 'silver'")

        # ── At least 4 trigger phrases ────────────────────────────────────────
        trigger_items = re.findall(r"^\s+-\s+\S", fm, re.MULTILINE)
        self.assertGreaterEqual(
            len(trigger_items), 4,
            f"approve-action must have at least 4 triggers, found {len(trigger_items)}",
        )

        # ── Required body sections ─────────────────────────────────────────────
        for section in ("## Purpose", "## Process", "## How to Run",
                        "## Expected Output", "## Dependencies", "## Notes"):
            self.assertIn(section, content, f"SKILL.md missing required section: '{section}'")

        # ── HITL gate must be mentioned ────────────────────────────────────────
        self.assertIn(
            "NEVER", content,
            "SKILL.md must include a NEVER auto-execute warning (HITL gate)",
        )

        # ── References correct execution modules ──────────────────────────────
        self.assertIn("email_server", content, "SKILL.md must reference 'email_server'")
        self.assertIn("linkedin_poster", content, "SKILL.md must reference 'linkedin_poster'")

        # ── No Python code blocks ──────────────────────────────────────────────
        python_blocks = re.findall(r"```python", content, re.IGNORECASE)
        self.assertEqual(
            len(python_blocks), 0,
            f"SKILL.md must not contain ```python blocks (found {len(python_blocks)})",
        )

        print(f"\n  Path       : {skill_path}")
        print(f"  Size       : {len(content):,} chars")
        print(f"  Frontmatter: name=approve-action, tier=silver, "
              f"triggers ({len(trigger_items)}) — OK")
        print(f"  All required sections present: OK")
        print(f"  HITL gate (NEVER) present: OK")
        print(f"  email_server + linkedin_poster references: OK")
        print(f"  No Python code blocks: OK")

    # ── 2. reject-action skill ────────────────────────────────────────────────

    def test_2_reject_skill_exists(self):
        """reject-action SKILL.md exists, has valid frontmatter, and is pure Markdown."""
        skill_path = self.project_path / ".claude" / "skills" / "reject-action" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"reject-action SKILL.md not found at: {skill_path}",
        )
        self.assertTrue(skill_path.is_file(), "reject-action path is not a file")

        content = skill_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 500, "reject-action SKILL.md is suspiciously short")

        # ── Frontmatter ───────────────────────────────────────────────────────
        self.assertTrue(content.startswith("---"), "SKILL.md must start with '---' frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter block not properly closed with '---'")

        fm = parts[1]

        for field in ("name:", "description:", "triggers:", "tier:"):
            self.assertIn(field, fm, f"reject-action frontmatter missing field: '{field}'")

        self.assertIn("reject-action", fm, "Frontmatter 'name' must be 'reject-action'")
        self.assertIn("silver", fm.lower(), "Frontmatter 'tier' must be 'silver'")

        # ── At least 4 trigger phrases ────────────────────────────────────────
        trigger_items = re.findall(r"^\s+-\s+\S", fm, re.MULTILINE)
        self.assertGreaterEqual(
            len(trigger_items), 4,
            f"reject-action must have at least 4 triggers, found {len(trigger_items)}",
        )

        # ── Required body sections ─────────────────────────────────────────────
        for section in ("## Purpose", "## Process", "## How to Run",
                        "## Expected Output", "## Dependencies", "## Notes"):
            self.assertIn(section, content, f"SKILL.md missing required section: '{section}'")

        # ── Rejection-specific requirements ────────────────────────────────────
        self.assertIn(
            "rejected_by", content,
            "SKILL.md must document the 'rejected_by' frontmatter field",
        )
        self.assertIn(
            "rejection_reason", content,
            "SKILL.md must document the 'rejection_reason' frontmatter field",
        )
        # Must note that rejected actions are NEVER executed
        self.assertIn(
            "NEVER", content,
            "SKILL.md must include a NEVER execute warning",
        )
        # Must distinguish human vs system rejection
        self.assertIn("human", content.lower(), "SKILL.md must mention 'human' rejection")
        self.assertIn("system", content.lower(), "SKILL.md must mention 'system' (timeout) rejection")

        # ── No Python code blocks ──────────────────────────────────────────────
        python_blocks = re.findall(r"```python", content, re.IGNORECASE)
        self.assertEqual(
            len(python_blocks), 0,
            f"SKILL.md must not contain ```python blocks (found {len(python_blocks)})",
        )

        print(f"\n  Path       : {skill_path}")
        print(f"  Size       : {len(content):,} chars")
        print(f"  Frontmatter: name=reject-action, tier=silver, "
              f"triggers ({len(trigger_items)}) — OK")
        print(f"  All required sections present: OK")
        print(f"  rejected_by + rejection_reason fields documented: OK")
        print(f"  human vs system rejection distinction: OK")
        print(f"  NEVER execute warning present: OK")
        print(f"  No Python code blocks: OK")

    # ── 3. Timeout checker file exists ────────────────────────────────────────

    def test_3_timeout_checker_exists(self):
        """scheduler/check_approvals.py exists and is a valid Python file."""
        checker_path = self.project_path / "scheduler" / "check_approvals.py"

        self.assertTrue(
            checker_path.exists(),
            f"scheduler/check_approvals.py not found at: {checker_path}",
        )
        self.assertTrue(checker_path.is_file(), "check_approvals.py path is not a file")
        self.assertEqual(checker_path.suffix, ".py", "check_approvals must be a .py file")

        source = checker_path.read_text(encoding="utf-8")
        self.assertGreater(len(source), 300, "check_approvals.py is suspiciously short")

        # Must compile without SyntaxError
        try:
            compile(source, str(checker_path), "exec")
        except SyntaxError as exc:
            self.fail(f"check_approvals.py has a syntax error: {exc}")

        # Key identifiers must appear in source
        for identifier in (
            "check_pending_approvals",
            "auto_reject_expired",
            "is_expired",
            "time_until_expiry",
            "update_dashboard_timeouts",
            "check_expiring_soon",
        ):
            self.assertIn(
                identifier, source,
                f"Expected identifier '{identifier}' not found in check_approvals.py",
            )

        # Must reference the approvals log
        self.assertIn("approvals.log", source, "check_approvals.py must reference 'approvals.log'")

        # Must reference dashboard_updater
        self.assertIn(
            "dashboard_updater", source,
            "check_approvals.py must import from helpers.dashboard_updater",
        )

        print(f"\n  Path       : {checker_path}")
        print(f"  Size       : {len(source):,} chars")
        print(f"  Syntax     : valid Python")
        print(f"  Identifiers: check_pending_approvals, auto_reject_expired, is_expired,")
        print(f"               time_until_expiry, update_dashboard_timeouts,")
        print(f"               check_expiring_soon — all present")
        print(f"  approvals.log reference: OK")
        print(f"  dashboard_updater import: OK")

    # ── 4. Timeout checker functions ──────────────────────────────────────────

    def test_4_timeout_checker_functions(self):
        """Timeout checker imports cleanly; all public functions exist with correct signatures."""
        from scheduler.check_approvals import (
            check_pending_approvals,
            auto_reject_expired,
            is_expired,
            time_until_expiry,
            update_dashboard_timeouts,
            check_expiring_soon,
        )

        # All must be callable
        for fn in (check_pending_approvals, auto_reject_expired, is_expired,
                   time_until_expiry, update_dashboard_timeouts, check_expiring_soon):
            self.assertTrue(callable(fn), f"{fn.__name__} is not callable")

        # ── check_pending_approvals(vault_path, dry_run) ──────────────────────
        sig    = inspect.signature(check_pending_approvals)
        params = list(sig.parameters.keys())
        self.assertIn("vault_path", params, "check_pending_approvals missing 'vault_path' param")
        self.assertIn("dry_run",    params, "check_pending_approvals missing 'dry_run' param")
        # dry_run must be optional
        self.assertIsNot(
            sig.parameters["dry_run"].default,
            inspect.Parameter.empty,
            "'dry_run' must have a default value (optional param)",
        )

        # ── Return dict has all required keys ─────────────────────────────────
        result = check_pending_approvals(str(self.vault_path), dry_run=True)
        self.assertIsInstance(result, dict, "check_pending_approvals must return a dict")
        for key in ("total_pending", "expired_count", "active_count",
                    "errors", "expired_files", "next_expiring"):
            self.assertIn(key, result, f"Return dict missing required key: '{key}'")

        self.assertIsInstance(result["total_pending"],  int,  "total_pending must be int")
        self.assertIsInstance(result["expired_count"],  int,  "expired_count must be int")
        self.assertIsInstance(result["active_count"],   int,  "active_count must be int")
        self.assertIsInstance(result["errors"],         list, "errors must be a list")
        self.assertIsInstance(result["expired_files"],  list, "expired_files must be a list")
        self.assertIn(
            result["next_expiring"], (None, *[{}]),
            "next_expiring must be None or a dict",
        )
        # More precise check: must be None or a dict
        self.assertTrue(
            result["next_expiring"] is None or isinstance(result["next_expiring"], dict),
            "next_expiring must be None or a dict",
        )

        # ── is_expired(ts) ────────────────────────────────────────────────────
        past_ts   = (datetime.now() - timedelta(hours=25)).isoformat()
        future_ts = (datetime.now() + timedelta(hours=23)).isoformat()

        self.assertTrue(is_expired(past_ts),    "is_expired must return True for past timestamp")
        self.assertFalse(is_expired(future_ts), "is_expired must return False for future timestamp")
        self.assertFalse(is_expired("not-a-date"), "is_expired must return False for invalid input")

        # ── time_until_expiry(ts) ─────────────────────────────────────────────
        hours_left = time_until_expiry(future_ts)
        self.assertIsInstance(hours_left, float, "time_until_expiry must return a float")
        self.assertGreater(hours_left, 0, "Hours left for a future timestamp must be > 0")

        hours_over = time_until_expiry(past_ts)
        self.assertLess(hours_over, 0, "Hours left for a past timestamp must be < 0")

        # ── check_expiring_soon(vault, hours) ─────────────────────────────────
        soon_sig    = inspect.signature(check_expiring_soon)
        soon_params = list(soon_sig.parameters.keys())
        self.assertIn("vault_path",    soon_params, "check_expiring_soon missing 'vault_path'")
        self.assertIn("warning_hours", soon_params, "check_expiring_soon missing 'warning_hours'")
        self.assertIsNot(
            soon_sig.parameters["warning_hours"].default,
            inspect.Parameter.empty,
            "'warning_hours' must have a default value",
        )

        soon_result = check_expiring_soon(str(self.vault_path))
        self.assertIsInstance(soon_result, list, "check_expiring_soon must return a list")

        print(f"\n  check_pending_approvals params : {params}")
        print(f"  Return keys: total_pending, expired_count, active_count,")
        print(f"               errors, expired_files, next_expiring — OK")
        print(f"  is_expired(past)   = True  — OK")
        print(f"  is_expired(future) = False — OK")
        print(f"  is_expired(invalid)= False — OK")
        print(f"  time_until_expiry(future) > 0 — OK")
        print(f"  time_until_expiry(past)   < 0 — OK")
        print(f"  check_expiring_soon returns list — OK")
        print(f"  All 6 functions callable with correct signatures: OK")

    # ── 5. Approval folder structure ──────────────────────────────────────────

    def test_5_approval_folders(self):
        """All approval workflow folders exist (or are created) and are writable."""
        folders = {
            "Pending_Approval": self.vault_path / "Pending_Approval",
            "Approved":         self.vault_path / "Approved",
            "Rejected":         self.vault_path / "Rejected",
            "Done":             self.vault_path / "Done",
        }

        for name, folder in folders.items():
            folder.mkdir(parents=True, exist_ok=True)

            self.assertTrue(folder.exists(), f"{name}/ folder could not be created at: {folder}")
            self.assertTrue(folder.is_dir(), f"{name}/ path exists but is not a directory")

            # Write-test: create and immediately remove a probe file
            probe = folder / ".write_test"
            try:
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                writable = True
            except OSError:
                writable = False

            self.assertTrue(writable, f"{name}/ is not writable: {folder}")

        print(f"\n  Pending_Approval/ : exists, writable — OK")
        print(f"  Approved/         : exists, writable — OK")
        print(f"  Rejected/         : exists, writable — OK")
        print(f"  Done/             : exists, writable — OK")
        print(f"  Vault root        : {self.vault_path}")

    # ── 6. Create mock approval ───────────────────────────────────────────────

    def test_6_create_mock_approval(self):
        """A well-formed approval file can be created in Pending_Approval/ and round-trip parsed."""
        import frontmatter as fm_lib

        pending_dir = self.vault_path / "Pending_Approval"
        pending_dir.mkdir(parents=True, exist_ok=True)

        timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_filename = f"TEST_APPROVAL_{timestamp}.md"
        file_path     = pending_dir / test_filename
        self._temp_files.append(test_filename)

        created_ts = datetime.now()
        expires_ts = created_ts + timedelta(hours=24)

        # ── Build the approval post ────────────────────────────────────────────
        body = (
            "# TEST APPROVAL\n\n"
            "This is a test approval file for unit testing.\n\n"
            "## Email Details\n\n"
            "**To:** test@example.com\n"
            "**Subject:** Unit test email\n\n"
            "## Email Body\n\n"
            "Hello, this is a test.\n\n"
            "## Attachments\n\nNone\n\n"
            "## To Approve\nMove this file to: Approved/\n\n"
            "## To Reject\nMove this file to: Rejected/\n\n"
            "## Rejection Reason (if rejected)\n[Human adds reason here]\n\n"
            "## Auto-Reject\nThis approval expires in 24 hours.\n"
        )

        post = fm_lib.Post(
            body,
            action_type="send_email",
            created=created_ts.isoformat(timespec="seconds"),
            expires=expires_ts.isoformat(timespec="seconds"),
            status="pending",
            priority="normal",
            sent_to="test@example.com",
            subject="Unit test email",
        )

        file_path.write_text(fm_lib.dumps(post), encoding="utf-8")

        self.assertTrue(file_path.exists(), f"Test approval file was not created: {file_path}")
        self.assertGreater(file_path.stat().st_size, 0, "Approval file is empty")

        # ── Round-trip parse ──────────────────────────────────────────────────
        parsed = fm_lib.load(str(file_path))

        # Required frontmatter fields
        for field in ("action_type", "created", "expires", "status", "priority"):
            self.assertIn(field, parsed, f"Approval file missing required frontmatter field: '{field}'")

        self.assertEqual(parsed["action_type"], "send_email", "action_type mismatch")
        self.assertEqual(parsed["status"],      "pending",    "status must be 'pending' on creation")
        self.assertEqual(parsed["priority"],    "normal",     "priority mismatch")
        self.assertEqual(parsed["sent_to"],     "test@example.com", "sent_to mismatch")

        # expires must parse as a valid ISO datetime
        try:
            expires_parsed = datetime.fromisoformat(str(parsed["expires"]))
        except ValueError:
            self.fail(f"'expires' is not a valid ISO timestamp: {parsed['expires']!r}")

        # expires must be roughly 24 hours from now
        hours_left = (expires_parsed - datetime.now()).total_seconds() / 3600
        self.assertGreater(hours_left, 20, "expires should be ~24h in the future")
        self.assertLess(hours_left,    25, "expires is unreasonably far in the future")

        # Required body sections
        content = file_path.read_text(encoding="utf-8")
        for section in ("## Email Body", "## To Approve", "## To Reject"):
            self.assertIn(section, content, f"Approval file body missing section: '{section}'")

        print(f"\n  File      : {file_path.name}")
        print(f"  Size      : {file_path.stat().st_size:,} bytes")
        print(f"  action_type: {parsed['action_type']}")
        print(f"  status    : {parsed['status']}")
        print(f"  expires   : {parsed['expires']}  ({hours_left:.1f}h from now)")
        print(f"  All required frontmatter fields present: OK")
        print(f"  All required body sections present: OK")
        print(f"  Round-trip parse: OK")

    # ── 7. Timeout detection and auto-rejection ───────────────────────────────

    def test_7_timeout_detection(self):
        """Timeout checker detects an expired approval, moves it to Rejected/, and updates it."""
        import frontmatter as fm_lib
        from scheduler.check_approvals import check_pending_approvals

        pending_dir  = self.vault_path / "Pending_Approval"
        rejected_dir = self.vault_path / "Rejected"
        pending_dir.mkdir(parents=True,  exist_ok=True)
        rejected_dir.mkdir(parents=True, exist_ok=True)

        timestamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_filename = f"TEST_EXPIRED_{timestamp}.md"
        pending_path  = pending_dir / test_filename
        self._temp_files.append(test_filename)

        # Create an approval that expired 2 hours ago
        created_ts = datetime.now() - timedelta(hours=26)
        expires_ts = datetime.now() - timedelta(hours=2)

        body = (
            "# TEST EXPIRED APPROVAL\n\n"
            "This file is intentionally backdated to test timeout detection.\n\n"
            "## Email Body\n\nTest expired email body.\n\n"
            "## Attachments\n\nNone\n"
        )
        post = fm_lib.Post(
            body,
            action_type="send_email",
            created=created_ts.isoformat(timespec="seconds"),
            expires=expires_ts.isoformat(timespec="seconds"),
            status="pending",
            priority="normal",
            sent_to="expired@example.com",
            subject="Expired test email",
        )
        pending_path.write_text(fm_lib.dumps(post), encoding="utf-8")
        self.assertTrue(pending_path.exists(), "Could not create expired test file")

        # ── Run the timeout checker ────────────────────────────────────────────
        result = check_pending_approvals(str(self.vault_path), dry_run=False)

        # ── Verify the file was counted as expired ─────────────────────────────
        self.assertIn(
            test_filename, result["expired_files"],
            f"Checker did not detect {test_filename} as expired",
        )
        self.assertGreaterEqual(result["expired_count"], 1, "expired_count must be >= 1")

        # ── File must have been moved out of Pending_Approval/ ─────────────────
        self.assertFalse(
            pending_path.exists(),
            f"Expired file still in Pending_Approval/ — should have been moved to Rejected/",
        )

        # ── File must now exist in Rejected/ ──────────────────────────────────
        rejected_path = rejected_dir / test_filename
        self.assertTrue(
            rejected_path.exists(),
            f"Expired file not found in Rejected/ at: {rejected_path}",
        )

        # ── Verify updated frontmatter ─────────────────────────────────────────
        rejected_post = fm_lib.load(str(rejected_path))

        self.assertEqual(
            rejected_post.get("status"), "rejected",
            f"status must be 'rejected' after auto-rejection, got: {rejected_post.get('status')!r}",
        )
        self.assertEqual(
            rejected_post.get("rejected_by"), "system",
            f"rejected_by must be 'system' for auto-rejection, got: {rejected_post.get('rejected_by')!r}",
        )
        self.assertIn(
            "rejected_at", rejected_post,
            "Rejected file must have 'rejected_at' frontmatter field",
        )
        # rejected_at must be a parseable ISO timestamp
        try:
            datetime.fromisoformat(str(rejected_post["rejected_at"]))
        except ValueError:
            self.fail(f"rejected_at is not valid ISO: {rejected_post['rejected_at']!r}")

        self.assertIn(
            "rejection_reason", rejected_post,
            "Rejected file must have 'rejection_reason' frontmatter field",
        )
        self.assertIn(
            "timeout", rejected_post["rejection_reason"].lower(),
            f"rejection_reason should mention 'timeout', got: {rejected_post['rejection_reason']!r}",
        )

        # ── Verify auto-rejection section appended to body ─────────────────────
        rejected_content = rejected_path.read_text(encoding="utf-8")
        self.assertIn(
            "AUTO-REJECTION", rejected_content,
            "Rejected file must contain an AUTO-REJECTION section in the body",
        )
        self.assertIn(
            "System (Automatic)", rejected_content,
            "Auto-rejection section must note 'System (Automatic)'",
        )

        # ── Verify log entry was written ──────────────────────────────────────
        log_file = self.project_path / "logs" / "approvals.log"
        self.assertTrue(log_file.exists(), "approvals.log must exist after a timeout rejection")

        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn(
            test_filename, log_content,
            f"approvals.log must contain an entry for {test_filename}",
        )
        self.assertIn(
            "AUTO_REJECTED", log_content,
            "approvals.log must contain an AUTO_REJECTED entry",
        )

        hours_over = abs((expires_ts - datetime.now()).total_seconds() / 3600)
        print(f"\n  Expired file  : {test_filename}")
        print(f"  Hours over limit: {hours_over:.1f}h")
        print(f"  Detected as expired: OK")
        print(f"  Moved from Pending_Approval/ to Rejected/: OK")
        print(f"  status = rejected: OK")
        print(f"  rejected_by = system: OK")
        print(f"  rejected_at is valid ISO: OK")
        print(f"  rejection_reason mentions 'timeout': OK")
        print(f"  AUTO-REJECTION section appended to body: OK")
        print(f"  approvals.log entry written: OK")

    # ── 8. Logs folder and approval logging ───────────────────────────────────

    def test_8_logs_folder(self):
        """logs/ folder exists (or is created), approvals.log is writable, format is correct."""
        logs_dir  = self.project_path / "logs"
        log_file  = logs_dir / "approvals.log"

        # Ensure logs/ exists
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.assertTrue(logs_dir.exists(), f"logs/ folder could not be created at: {logs_dir}")
        self.assertTrue(logs_dir.is_dir(), "logs/ path is not a directory")

        # ── Write a test log entry ─────────────────────────────────────────────
        now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_entry = f"[{now_str}] TEST | Unit test log entry — will not appear in production\n"

        try:
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(test_entry)
            write_ok = True
        except OSError as exc:
            write_ok = False
            self.fail(f"Cannot write to approvals.log: {exc}")

        self.assertTrue(write_ok, "approvals.log is not writable")
        self.assertTrue(log_file.exists(), "approvals.log file does not exist after write")

        # ── Verify the entry was actually written ──────────────────────────────
        content = log_file.read_text(encoding="utf-8")
        self.assertIn(test_entry.strip(), content, "Test log entry not found after writing")

        # ── Verify log line format: [YYYY-MM-DD HH:MM:SS] LABEL | ... ─────────
        log_lines = [ln for ln in content.splitlines() if ln.strip()]
        for line in log_lines[-10:]:          # only check recent lines
            # Every non-empty line must start with a bracketed timestamp
            if not line.startswith("["):
                continue
            self.assertRegex(
                line,
                r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]",
                f"Log line does not match expected format: {line!r}",
            )

        # ── Verify expected log labels exist (from test_7 if it ran) ──────────
        #    These checks are informational — test_7 may not have run yet in all
        #    orderings, so we only assert the format, not specific entries.
        valid_labels = {"TEST", "TIMEOUT_CHECK", "AUTO_REJECTED", "REASON",
                        "APPROVED", "EXECUTED", "REJECTED"}
        found_labels: set[str] = set()
        for line in content.splitlines():
            match = re.search(r"\] ([A-Z_]+) \|", line)
            if match:
                found_labels.add(match.group(1))

        # At least the TEST label we just wrote must be present
        self.assertIn("TEST", found_labels, "TEST label not found in log file")

        line_count = len([l for l in content.splitlines() if l.strip()])
        known_found = valid_labels & found_labels

        print(f"\n  logs/ dir    : {logs_dir}")
        print(f"  approvals.log: {log_file}")
        print(f"  Writable     : OK")
        print(f"  Line count   : {line_count}")
        print(f"  Log format   : [YYYY-MM-DD HH:MM:SS] LABEL | ... — OK")
        print(f"  Labels found : {sorted(known_found)}")
        print(f"  TEST entry confirmed in file: OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestApprovalWorkflow)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  APPROVAL WORKFLOW — INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
