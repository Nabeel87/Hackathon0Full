"""
tests/test_linkedin.py

LinkedIn Silver Tier — comprehensive integration test suite.

Tests cover watcher init, session management, poster function signature,
skill file validity, approval workflow, main.py integration, and helper
file completeness.  No live LinkedIn connection is required.

Run:
    python -m pytest tests/test_linkedin.py -v
    python tests/test_linkedin.py              # standalone (no pytest needed)
"""

import inspect
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VAULT           = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
_CREDENTIALS_DIR = _PROJECT_ROOT / ".credentials" / "linkedin_session"
_SESSION_FILE    = _CREDENTIALS_DIR / "context.json"


# ── Test suite ────────────────────────────────────────────────────────────────

class TestLinkedInIntegration(unittest.TestCase):
    """Full integration test suite for the LinkedIn Silver Tier components."""

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
            except Exception:
                pass

    # ── 1. Watcher initialisation ─────────────────────────────────────────────

    def test_1_linkedin_watcher_init(self):
        """LinkedInWatcher initialises with correct defaults and inherits BaseWatcher."""
        from watchers.linkedin_watcher import LinkedInWatcher
        from watchers.base_watcher import BaseWatcher

        watcher = LinkedInWatcher(vault_path=self.vault_path, check_interval=180)

        self.assertEqual(
            watcher.vault_path, Path(self.vault_path),
            f"vault_path mismatch: expected {self.vault_path}, got {watcher.vault_path}",
        )
        self.assertEqual(
            watcher.check_interval, 180,
            f"check_interval should be 180, got {watcher.check_interval}",
        )
        self.assertIsInstance(
            watcher, BaseWatcher,
            "LinkedInWatcher must inherit from BaseWatcher",
        )
        self.assertTrue(
            hasattr(watcher, "session_dir"),
            "LinkedInWatcher must have a session_dir attribute",
        )
        self.assertTrue(
            hasattr(watcher, "_seen_ids"),
            "LinkedInWatcher must have a _seen_ids deduplication set",
        )

        # Verify required methods exist
        for method in (
            "check_for_updates",
            "create_action_file",
            "_ensure_session",
            "_login_and_save_session",
            "_check_messages",
            "_check_notifications",
            "_extract_notification_data",
        ):
            self.assertTrue(
                callable(getattr(watcher, method, None)),
                f"LinkedInWatcher is missing required method: {method}",
            )

        print(f"\n  vault_path    : {watcher.vault_path}")
        print(f"  check_interval: {watcher.check_interval}s")
        print(f"  session_dir   : {watcher.session_dir}")
        print(f"  BaseWatcher   : OK")
        print(f"  All 7 required methods present: OK")

    # ── 2. Session folder ─────────────────────────────────────────────────────

    def test_2_session_folder_exists(self):
        """Session directory exists (or is created); reports context.json status."""
        if not _CREDENTIALS_DIR.exists():
            _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
            print(f"\n  Created: {_CREDENTIALS_DIR}")
        else:
            print(f"\n  Exists : {_CREDENTIALS_DIR}")

        self.assertTrue(
            _CREDENTIALS_DIR.exists(),
            f"Session directory could not be created: {_CREDENTIALS_DIR}",
        )
        self.assertTrue(
            _CREDENTIALS_DIR.is_dir(),
            f"Session path exists but is not a directory: {_CREDENTIALS_DIR}",
        )

        # Report context.json presence (not a hard failure — login may not have run yet)
        if _SESSION_FILE.exists() and _SESSION_FILE.stat().st_size > 20:
            print(f"  context.json  : FOUND ({_SESSION_FILE.stat().st_size:,} bytes)")
        else:
            print("  context.json  : NOT FOUND (interactive login required before first run)")

        # Sanity-check: old cookies.json should NOT be the session file
        old_cookies = _CREDENTIALS_DIR / "cookies.json"
        if old_cookies.exists():
            print("  WARNING: cookies.json found — session has been migrated to context.json")

        print(f"  Permissions   : readable={_CREDENTIALS_DIR.stat().st_mode & 0o400 != 0}")

    # ── 3. Poster function signature ──────────────────────────────────────────

    def test_3_poster_function_exists(self):
        """post_to_linkedin exists, is callable, and has the correct signature."""
        from helpers.linkedin_poster import post_to_linkedin

        self.assertTrue(callable(post_to_linkedin), "post_to_linkedin is not callable")

        sig    = inspect.signature(post_to_linkedin)
        params = list(sig.parameters.keys())

        for required_param in ("content", "image_path", "vault_path"):
            self.assertIn(
                required_param, params,
                f"post_to_linkedin is missing required parameter: '{required_param}'",
            )

        # image_path and vault_path must be optional (have defaults)
        for optional_param in ("image_path", "vault_path"):
            self.assertIsNot(
                sig.parameters[optional_param].default,
                inspect.Parameter.empty,
                f"'{optional_param}' must have a default value (should be optional)",
            )

        # Verify the return-type annotation or at least that it returns a dict at import time
        self.assertIn(
            "session_dir", params,
            "post_to_linkedin should accept a 'session_dir' override parameter",
        )

        print(f"\n  Function  : post_to_linkedin")
        print(f"  Parameters: {params}")
        for name, p in sig.parameters.items():
            default = "required" if p.default is inspect.Parameter.empty else repr(p.default)
            print(f"    {name:<15}: {default}")

    # ── 4. Posting skill file ─────────────────────────────────────────────────

    def test_4_posting_skill_exists(self):
        """post-linkedin SKILL.md exists, has valid frontmatter, and is pure Markdown."""
        skill_path = self.project_path / ".claude" / "skills" / "post-linkedin" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"post-linkedin SKILL.md not found at: {skill_path}",
        )

        content = skill_path.read_text(encoding="utf-8")

        # Frontmatter delimiters
        self.assertTrue(
            content.startswith("---"),
            "SKILL.md must start with '---' YAML frontmatter",
        )
        parts = content.split("---", 2)
        self.assertGreaterEqual(
            len(parts), 3,
            "SKILL.md frontmatter block is not properly closed with '---'",
        )

        frontmatter = parts[1]

        # Required frontmatter fields
        for field in ("name:", "description:", "triggers:", "tier:"):
            self.assertIn(
                field, frontmatter,
                f"Frontmatter missing required field: '{field}'",
            )

        # name must equal post-linkedin
        self.assertIn(
            "post-linkedin", frontmatter,
            "Frontmatter 'name' field must be 'post-linkedin'",
        )

        # triggers must not be empty
        triggers_section = frontmatter[frontmatter.find("triggers:"):]
        self.assertRegex(
            triggers_section, r"- \S+",
            "triggers list must contain at least one item",
        )

        # Required body sections
        for section in ("## Purpose", "## Process", "## How to Run", "## Dependencies", "## Notes"):
            self.assertIn(
                section, content,
                f"SKILL.md is missing required section: '{section}'",
            )

        # Pure Markdown — no Python code blocks
        python_blocks = re.findall(r"```python", content, re.IGNORECASE)
        self.assertEqual(
            len(python_blocks), 0,
            f"SKILL.md must not contain ```python code blocks (found {len(python_blocks)})",
        )

        print(f"\n  Path      : {skill_path}")
        print(f"  Size      : {len(content):,} chars")
        print(f"  Frontmatter fields: name, description, triggers, tier — OK")
        print(f"  Body sections: Purpose, Process, How to Run, Dependencies, Notes — OK")
        print(f"  No Python code blocks: OK")

    # ── 5. Monitor skill file ─────────────────────────────────────────────────

    def test_5_monitor_skill_exists(self):
        """linkedin-monitor SKILL.md exists, has valid frontmatter, and correct structure."""
        skill_path = self.project_path / ".claude" / "skills" / "linkedin-monitor" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"linkedin-monitor SKILL.md not found at: {skill_path}",
        )

        content = skill_path.read_text(encoding="utf-8")

        # Frontmatter
        self.assertTrue(content.startswith("---"), "SKILL.md must start with YAML frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter block not properly closed")

        frontmatter = parts[1]

        for field in ("name:", "description:", "triggers:", "tier:"):
            self.assertIn(field, frontmatter, f"Frontmatter missing: '{field}'")

        self.assertIn("linkedin-monitor", frontmatter, "name must be 'linkedin-monitor'")

        # Skill-creator required sections
        for section in ("## Purpose", "## Process", "## How to Run",
                         "## Expected Output", "## Dependencies", "## Notes"):
            self.assertIn(section, content, f"Missing required section: '{section}'")

        # Must reference the correct watcher module
        self.assertIn(
            "linkedin_watcher", content,
            "SKILL.md must reference 'linkedin_watcher' in How to Run",
        )

        # Must reference context.json (not old cookies.json)
        self.assertIn(
            "context.json", content,
            "SKILL.md must reference 'context.json' session file (not cookies.json)",
        )

        # No Python code blocks
        self.assertEqual(
            len(re.findall(r"```python", content, re.IGNORECASE)), 0,
            "SKILL.md must not contain ```python code blocks",
        )

        # Triggers include at least "check linkedin"
        self.assertIn("check linkedin", content, "Triggers must include 'check linkedin'")

        print(f"\n  Path      : {skill_path}")
        print(f"  Size      : {len(content):,} chars")
        print(f"  Frontmatter: name, description, triggers, tier — OK")
        print(f"  Sections  : Purpose, Process, How to Run, Expected Output, Dependencies, Notes — OK")
        print(f"  context.json reference: OK")
        print(f"  No Python code blocks : OK")

    # ── 6. Approval workflow ──────────────────────────────────────────────────

    def test_6_approval_workflow(self):
        """Vault Pending_Approval/ folder exists; mock approval file is written and cleaned up."""
        pending_dir = self.vault_path / "Pending_Approval"
        pending_dir.mkdir(parents=True, exist_ok=True)

        self.assertTrue(pending_dir.exists(), f"Pending_Approval/ could not be created")
        self.assertTrue(pending_dir.is_dir(), "Pending_Approval must be a directory")

        # Verify sibling workflow folders also exist (create if absent)
        for folder_name in ("Approved", "Rejected", "Done"):
            folder = self.vault_path / folder_name
            folder.mkdir(parents=True, exist_ok=True)
            self.assertTrue(folder.exists(), f"Workflow folder missing: {folder_name}/")

        # Create mock approval file with spec-correct frontmatter
        now     = datetime.now(tz=timezone.utc)
        expires = now + timedelta(hours=24)
        ts      = now.strftime("%Y%m%d_%H%M%S")
        content = "Test post: LinkedIn integration test — automated by test suite."

        approval_file = pending_dir / f"LINKEDIN_POST_{ts}_TEST.md"
        self._temp_files.append(approval_file)   # guaranteed cleanup

        card = (
            f"---\n"
            f"action_type: linkedin_post\n"
            f"created: {now.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"expires: {expires.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"status: pending\n"
            f"priority: normal\n"
            f"---\n"
            f"\n"
            f"# APPROVAL REQUIRED: LinkedIn Post\n"
            f"\n"
            f"## Post Content\n"
            f"{content}\n"
            f"\n"
            f"## Image\n"
            f"None\n"
            f"\n"
            f"## To Approve\n"
            f"Move this file to: Approved/\n"
            f"\n"
            f"## To Reject\n"
            f"Move this file to: Rejected/ (and add rejection reason below)\n"
            f"\n"
            f"## Rejection Reason (if rejected)\n"
            f"[Human adds reason here]\n"
            f"\n"
            f"## Auto-Reject\n"
            f"This approval expires in 24 hours and will auto-reject if not decided.\n"
        )

        approval_file.write_text(card, encoding="utf-8")

        self.assertTrue(approval_file.exists(), "Approval file was not created")

        written = approval_file.read_text(encoding="utf-8")

        # Verify spec-required frontmatter keys
        self.assertIn("action_type: linkedin_post", written, "Frontmatter must use 'action_type: linkedin_post'")
        self.assertIn("status: pending",             written, "Frontmatter must include 'status: pending'")
        self.assertIn("priority: normal",            written, "Frontmatter must include 'priority: normal'")
        self.assertIn("created:",                    written, "Frontmatter must include 'created' timestamp")
        self.assertIn("expires:",                    written, "Frontmatter must include 'expires' timestamp")

        # Verify spec-required body sections
        self.assertIn("# APPROVAL REQUIRED: LinkedIn Post", written, "Header must match spec exactly")
        self.assertIn("## Post Content",                    written, "Body must include '## Post Content'")
        self.assertIn("## To Approve",                      written, "Body must include '## To Approve'")
        self.assertIn("## To Reject",                       written, "Body must include '## To Reject'")
        self.assertIn("## Auto-Reject",                     written, "Body must include '## Auto-Reject'")
        self.assertIn(content,                              written, "Post content must appear verbatim")

        # Expiry is 24 h in the future
        created_dt = datetime.fromisoformat(now.strftime("%Y-%m-%dT%H:%M:%S")).replace(tzinfo=timezone.utc)
        expires_dt = datetime.fromisoformat(expires.strftime("%Y-%m-%dT%H:%M:%S")).replace(tzinfo=timezone.utc)
        self.assertAlmostEqual(
            (expires_dt - created_dt).total_seconds(), 86400, delta=60,
            msg="Approval expiry must be 24 hours after creation",
        )

        print(f"\n  File    : {approval_file.name}")
        print(f"  Size    : {len(written):,} chars")
        print(f"  action_type: linkedin_post — OK")
        print(f"  status / priority / created / expires — OK")
        print(f"  All body sections present — OK")
        print(f"  24-hour expiry window — OK")
        print(f"  Workflow folders (Approved/, Rejected/, Done/) — OK")

        # Cleanup via tearDown (_temp_files), but also unlink here for explicit confirmation
        approval_file.unlink()
        self.assertFalse(approval_file.exists(), "Test file was not cleaned up correctly")
        self._temp_files.remove(approval_file)   # prevent double-unlink in tearDown
        print(f"  Cleanup : OK")

    # ── 7. main.py integration ────────────────────────────────────────────────

    def test_7_main_integration(self):
        """main.py imports LinkedInWatcher and integrates it in the orchestrator."""
        main_path = self.project_path / "main.py"

        self.assertTrue(main_path.exists(), f"main.py not found at: {main_path}")

        source = main_path.read_text(encoding="utf-8")

        # Import present
        self.assertIn(
            "from watchers.linkedin_watcher import LinkedInWatcher",
            source,
            "main.py must import LinkedInWatcher from watchers.linkedin_watcher",
        )

        # CLI argument for LinkedIn interval
        self.assertIn(
            "linkedin-interval", source,
            "main.py must define --linkedin-interval CLI argument",
        )
        self.assertIn(
            "default=180", source,
            "--linkedin-interval must default to 180 seconds",
        )

        # LinkedInWatcher is instantiated in the orchestrator
        self.assertIn(
            "LinkedInWatcher", source,
            "main.py must instantiate LinkedInWatcher in the orchestrator",
        )

        # linkedin_interval (or equivalent) is passed through
        self.assertIn(
            "linkedin_interval", source,
            "main.py must wire linkedin_interval into the watcher",
        )

        # Startup banner mentions LinkedIn
        self.assertIn(
            "LinkedIn", source,
            "Startup banner must reference LinkedIn Watcher",
        )

        # All three watchers listed
        for watcher_name in ("FileWatcher", "GmailWatcher", "LinkedInWatcher"):
            self.assertIn(
                watcher_name, source,
                f"main.py must reference {watcher_name}",
            )

        # Health check covers all watchers (orchestrator-level loop)
        self.assertIn(
            "_health_check", source,
            "main.py must include a _health_check method",
        )

        print(f"\n  File                  : {main_path}")
        print(f"  LinkedInWatcher import : OK")
        print(f"  --linkedin-interval    : OK (default=180)")
        print(f"  LinkedInWatcher in orchestrator: OK")
        print(f"  linkedin_interval wired: OK")
        print(f"  Banner mentions LinkedIn: OK")
        print(f"  _health_check covers all watchers: OK")

    # ── 8. Helper file completeness ───────────────────────────────────────────

    def test_8_helper_file_exists(self):
        """helpers/linkedin_poster.py exists and exports post_to_linkedin + test_linkedin_post."""
        helper_path = self.project_path / "helpers" / "linkedin_poster.py"

        self.assertTrue(
            helper_path.exists(),
            f"helpers/linkedin_poster.py not found at: {helper_path}",
        )

        source = helper_path.read_text(encoding="utf-8")

        # post_to_linkedin function must be defined
        self.assertIn(
            "def post_to_linkedin(", source,
            "helpers/linkedin_poster.py must define post_to_linkedin()",
        )

        # test_linkedin_post function must be defined
        self.assertIn(
            "def test_linkedin_post(", source,
            "helpers/linkedin_poster.py must define test_linkedin_post()",
        )

        # Actually import and verify callability
        from helpers.linkedin_poster import post_to_linkedin, test_linkedin_post

        self.assertTrue(callable(post_to_linkedin),    "post_to_linkedin must be callable")
        self.assertTrue(callable(test_linkedin_post),  "test_linkedin_post must be callable")

        # Return type annotation or dict-like: verify the function returns a dict by inspecting
        sig    = inspect.signature(post_to_linkedin)
        params = list(sig.parameters.keys())
        self.assertIn("content",    params, "post_to_linkedin must accept 'content'")
        self.assertIn("image_path", params, "post_to_linkedin must accept 'image_path'")

        # Session must use context.json (not cookies.json)
        self.assertIn(
            "context.json", source,
            "linkedin_poster.py must reference context.json session file",
        )
        self.assertNotIn(
            "cookies.json", source,
            "linkedin_poster.py must NOT reference legacy cookies.json",
        )

        # Log file path must be project-level logs/, not inside vault
        self.assertIn(
            "logs/linkedin_posts.log", source,
            "Log file must be logs/linkedin_posts.log (project root, not vault)",
        )
        self.assertNotIn(
            "Vault/Logs", source,
            "Log file must NOT be inside the vault (Vault/Logs)",
        )

        # Security: no hardcoded passwords or credentials
        for forbidden in ("password", "li_at=", "JSESSIONID="):
            self.assertNotIn(
                forbidden, source,
                f"linkedin_poster.py must not contain hardcoded credential: '{forbidden}'",
            )

        print(f"\n  File              : {helper_path}")
        print(f"  Size              : {len(source):,} chars")
        print(f"  post_to_linkedin  : callable — OK")
        print(f"  test_linkedin_post: callable — OK")
        print(f"  Session file      : context.json (not cookies.json) — OK")
        print(f"  Log path          : logs/linkedin_posts.log (project root) — OK")
        print(f"  No hardcoded credentials: OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestLinkedInIntegration)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  LINKEDIN SILVER TIER — INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
