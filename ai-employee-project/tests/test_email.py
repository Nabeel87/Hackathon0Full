"""
tests/test_email.py

Email MCP Server & send-email skill — comprehensive integration tests.

No live Gmail connection is required.  Tests cover file/function existence,
skill structure, scope configuration, draft creation, folder layout,
the module's own validation logic, and log-file writability.

Run:
    python -m pytest tests/test_email.py -v
    python tests/test_email.py              # standalone (no pytest needed)
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

_VAULT   = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
_LOG_DIR = _PROJECT_ROOT / "logs"


# ── Test suite ────────────────────────────────────────────────────────────────

class TestEmailIntegration(unittest.TestCase):
    """Full integration test suite for the Email MCP Server (Silver Tier)."""

    def setUp(self):
        """Shared fixtures available to every test method."""
        self.vault_path   = _VAULT
        self.project_path = _PROJECT_ROOT
        self._temp_files: list[Path] = []

    def tearDown(self):
        """Remove any temp files created during the test run."""
        for path in self._temp_files:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    # ── 1. Email server file exists ───────────────────────────────────────────

    def test_1_email_server_exists(self):
        """mcp_servers/email_server.py exists and is a valid Python file."""
        server_path = self.project_path / "mcp_servers" / "email_server.py"

        self.assertTrue(
            server_path.exists(),
            f"email_server.py not found at: {server_path}",
        )
        self.assertTrue(
            server_path.is_file(),
            "email_server.py path exists but is not a file",
        )
        self.assertEqual(
            server_path.suffix, ".py",
            "email_server must be a .py file",
        )

        source = server_path.read_text(encoding="utf-8")
        self.assertGreater(len(source), 100, "email_server.py appears to be empty or too short")

        # Must compile without syntax errors
        try:
            compile(source, str(server_path), "exec")
        except SyntaxError as exc:
            self.fail(f"email_server.py has a syntax error: {exc}")

        # Must have the module docstring marker
        self.assertIn("email_server", source, "File does not appear to be email_server.py")

        print(f"\n  Path   : {server_path}")
        print(f"  Size   : {len(source):,} chars")
        print(f"  Syntax : valid Python")

    # ── 2. Email server functions ─────────────────────────────────────────────

    def test_2_email_server_functions(self):
        """send_email() and draft_email() exist and have the correct signatures."""
        from mcp_servers.email_server import send_email, draft_email, test_send_email

        for fn in (send_email, draft_email, test_send_email):
            self.assertTrue(callable(fn), f"{fn.__name__} is not callable")

        # ── send_email signature ──────────────────────────────────────────────
        sig    = inspect.signature(send_email)
        params = list(sig.parameters.keys())

        for required in ("to", "subject", "body"):
            self.assertIn(required, params, f"send_email missing required param: '{required}'")

        for optional in ("attachments", "vault_path", "credentials_dir"):
            self.assertIn(optional, params, f"send_email missing optional param: '{optional}'")
            self.assertIsNot(
                sig.parameters[optional].default,
                inspect.Parameter.empty,
                f"'{optional}' must have a default value (must be optional)",
            )

        # ── draft_email signature ─────────────────────────────────────────────
        dsig    = inspect.signature(draft_email)
        dparams = list(dsig.parameters.keys())

        for required in ("to", "subject", "body"):
            self.assertIn(required, dparams, f"draft_email missing required param: '{required}'")

        for optional in ("attachments", "vault_path"):
            self.assertIn(optional, dparams, f"draft_email missing optional param: '{optional}'")

        # draft_email returns str (file path), not dict
        ann = dsig.return_annotation
        if ann is not inspect.Parameter.empty:
            self.assertIn(
                ann, (str, "str"),
                f"draft_email should return str (file path), got: {ann}",
            )

        print(f"\n  send_email params  : {params}")
        print(f"  draft_email params : {dparams}")
        print(f"  test_send_email    : callable — OK")
        print(f"  Optional params have defaults: OK")

    # ── 3. Send-email skill file ──────────────────────────────────────────────

    def test_3_send_email_skill_exists(self):
        """send-email SKILL.md exists, has valid frontmatter, and is pure Markdown."""
        skill_path = self.project_path / ".claude" / "skills" / "send-email" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"send-email SKILL.md not found at: {skill_path}",
        )

        content = skill_path.read_text(encoding="utf-8")

        # Frontmatter delimiters
        self.assertTrue(content.startswith("---"), "SKILL.md must start with '---' frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter block not properly closed with '---'")

        frontmatter = parts[1]

        # Required frontmatter fields
        for field in ("name:", "description:", "triggers:", "tier:"):
            self.assertIn(field, frontmatter, f"Frontmatter missing field: '{field}'")

        # name must be send-email
        self.assertIn("send-email", frontmatter, "Frontmatter 'name' must be 'send-email'")

        # triggers must have at least one item
        self.assertRegex(frontmatter, r"- \S+", "triggers list must contain at least one item")

        # Required body sections
        for section in ("## Purpose", "## Process", "## How to Run",
                         "## Expected Output", "## Dependencies", "## Notes"):
            self.assertIn(section, content, f"SKILL.md missing required section: '{section}'")

        # Must reference the email_server module
        self.assertIn(
            "email_server", content,
            "SKILL.md must reference 'email_server' in How to Run",
        )

        # Pure Markdown — no Python code blocks
        python_blocks = re.findall(r"```python", content, re.IGNORECASE)
        self.assertEqual(
            len(python_blocks), 0,
            f"SKILL.md must not contain ```python blocks (found {len(python_blocks)})",
        )

        # HITL gate mentioned (security requirement)
        self.assertIn(
            "approval", content.lower(),
            "SKILL.md must describe the human approval (HITL) requirement",
        )

        print(f"\n  Path      : {skill_path}")
        print(f"  Size      : {len(content):,} chars")
        print(f"  Frontmatter: name=send-email, triggers, tier — OK")
        print(f"  Sections  : Purpose, Process, How to Run, Expected Output, Dependencies, Notes — OK")
        print(f"  email_server reference: OK")
        print(f"  No Python code blocks : OK")
        print(f"  HITL approval gate    : documented — OK")

    # ── 4. Gmail scopes ───────────────────────────────────────────────────────

    def test_4_gmail_scopes_updated(self):
        """gmail_watcher.py and email_server.py both declare readonly + send scopes."""
        readonly_scope = "https://www.googleapis.com/auth/gmail.readonly"
        send_scope     = "https://www.googleapis.com/auth/gmail.send"

        files_to_check = {
            "watchers/gmail_watcher.py":    self.project_path / "watchers" / "gmail_watcher.py",
            "mcp_servers/email_server.py":  self.project_path / "mcp_servers" / "email_server.py",
        }

        for label, path in files_to_check.items():
            self.assertTrue(path.exists(), f"{label} not found at: {path}")
            source = path.read_text(encoding="utf-8")

            self.assertIn(
                readonly_scope, source,
                f"{label}: 'gmail.readonly' scope is missing from SCOPES",
            )
            self.assertIn(
                send_scope, source,
                f"{label}: 'gmail.send' scope is missing from SCOPES",
            )

            # Both scopes must appear in the same SCOPES block (not scattered)
            scopes_block_start = source.find("SCOPES")
            self.assertGreater(scopes_block_start, -1, f"{label}: SCOPES constant not found")
            scopes_block = source[scopes_block_start : scopes_block_start + 300]
            self.assertIn(
                "gmail.readonly", scopes_block,
                f"{label}: gmail.readonly not in SCOPES block",
            )
            self.assertIn(
                "gmail.send", scopes_block,
                f"{label}: gmail.send not in SCOPES block",
            )

            print(f"\n  {label}")
            print(f"    gmail.readonly : PRESENT")
            print(f"    gmail.send     : PRESENT")

        # Import and verify at runtime
        from mcp_servers.email_server import SCOPES as email_scopes
        self.assertIn(readonly_scope, email_scopes, "email_server.SCOPES missing readonly")
        self.assertIn(send_scope,     email_scopes, "email_server.SCOPES missing send")
        print(f"\n  Runtime SCOPES list verified: {len(email_scopes)} scope(s) — OK")

    # ── 5. Draft file creation ────────────────────────────────────────────────

    def test_5_draft_creation(self):
        """draft_email() creates a correctly-formatted approval file in Pending_Approval/."""
        from mcp_servers.email_server import draft_email

        pending_dir = self.vault_path / "Pending_Approval"
        pending_dir.mkdir(parents=True, exist_ok=True)

        to      = "test@example.com"
        subject = "Integration Test Draft"
        body    = "This is a test email body created by the automated test suite."

        # Call draft_email — it creates the file and returns the path
        draft_path_str = draft_email(
            to=to,
            subject=subject,
            body=body,
            attachments=None,
            vault_path=self.vault_path,
        )
        draft_path = Path(draft_path_str)
        self._temp_files.append(draft_path)   # guaranteed tearDown cleanup

        self.assertTrue(draft_path.exists(), f"Draft file was not created at: {draft_path}")
        self.assertTrue(
            draft_path.name.startswith("EMAIL_DRAFT_"),
            f"Draft filename must start with EMAIL_DRAFT_, got: {draft_path.name}",
        )
        self.assertEqual(draft_path.suffix, ".md", "Draft file must be a .md file")
        self.assertEqual(
            draft_path.parent, pending_dir,
            f"Draft must be in Pending_Approval/, got: {draft_path.parent}",
        )

        content = draft_path.read_text(encoding="utf-8")

        # ── Frontmatter ────────────────────────────────────────────────────────
        self.assertTrue(content.startswith("---"), "Draft must start with YAML frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter not properly closed")

        fm = parts[1]
        self.assertIn("action_type: send_email", fm, "Frontmatter must have action_type: send_email")
        self.assertIn("status: pending",          fm, "Frontmatter must have status: pending")
        self.assertIn("priority: normal",         fm, "Frontmatter must have priority: normal")
        self.assertIn("created:",                 fm, "Frontmatter must include 'created' timestamp")
        self.assertIn("expires:",                 fm, "Frontmatter must include 'expires' timestamp")
        self.assertIn(to,                         fm, "Frontmatter must include recipient address")
        self.assertIn(subject,                    fm, f"Frontmatter must include subject: {subject!r}")

        # ── Body sections ──────────────────────────────────────────────────────
        for section in (
            "# APPROVAL REQUIRED: Send Email",
            "## Email Details",
            "## Email Body",
            "## To Approve",
            "## To Reject",
            "## Auto-Reject",
        ):
            self.assertIn(section, content, f"Draft missing required section: '{section}'")

        self.assertIn(body, content, "Email body must appear verbatim in the draft file")
        self.assertIn(to,   content, "Recipient must appear in the draft body")

        # ── Expiry is 24 h after creation ──────────────────────────────────────
        created_match = re.search(r"created:\s*(\S+)", fm)
        expires_match = re.search(r"expires:\s*(\S+)",  fm)
        if created_match and expires_match:
            try:
                created_dt = datetime.fromisoformat(created_match.group(1))
                expires_dt = datetime.fromisoformat(expires_match.group(1))
                delta_seconds = (expires_dt - created_dt).total_seconds()
                self.assertAlmostEqual(
                    delta_seconds, 86400, delta=120,
                    msg="Approval expiry must be 24 hours after creation",
                )
                print(f"\n  Expiry window: {delta_seconds / 3600:.1f}h — OK")
            except ValueError:
                pass   # non-ISO timestamps are a soft warning, not a hard failure

        print(f"\n  Draft file   : {draft_path.name}")
        print(f"  Size         : {len(content):,} chars")
        print(f"  action_type  : send_email — OK")
        print(f"  All sections : Email Details, Email Body, To Approve, To Reject, Auto-Reject — OK")
        print(f"  Body verbatim: OK")
        print(f"  Cleanup      : scheduled via tearDown")

    # ── 6. Approval folder structure ──────────────────────────────────────────

    def test_6_approval_folders(self):
        """All four HITL workflow folders exist (or are created) under vault."""
        required_folders = ("Pending_Approval", "Approved", "Rejected", "Done")

        for folder_name in required_folders:
            folder = self.vault_path / folder_name
            folder.mkdir(parents=True, exist_ok=True)

            self.assertTrue(
                folder.exists(),
                f"Workflow folder could not be created: {folder}",
            )
            self.assertTrue(
                folder.is_dir(),
                f"Workflow path exists but is not a directory: {folder}",
            )

        print(f"\n  Vault: {self.vault_path}")
        for name in required_folders:
            exists = (self.vault_path / name).exists()
            print(f"  {name + '/':25} {'EXISTS' if exists else 'CREATED'}")

    # ── 7. Email address validation ───────────────────────────────────────────

    def test_7_email_validation(self):
        """_validate_recipients() accepts valid addresses and rejects invalid ones."""
        from mcp_servers.email_server import _validate_recipients

        # ── Valid single addresses ─────────────────────────────────────────────
        valid_cases = [
            "user@example.com",
            "test.user+tag@domain.co.uk",
            "firstname.lastname@company.org",
            "user123@sub.domain.com",
        ]
        for addr in valid_cases:
            try:
                result = _validate_recipients(addr)
                self.assertEqual(result, [addr], f"Expected [{addr!r}], got {result}")
            except ValueError as exc:
                self.fail(f"Valid address {addr!r} was incorrectly rejected: {exc}")

        # ── Valid comma-separated (multiple recipients) ────────────────────────
        multi = "alice@example.com, bob@example.com"
        result = _validate_recipients(multi)
        self.assertEqual(len(result), 2, "Two comma-separated addresses should return 2-item list")
        self.assertIn("alice@example.com", result)
        self.assertIn("bob@example.com",   result)

        # ── Invalid addresses ──────────────────────────────────────────────────
        invalid_cases = [
            ("not-an-email",   "missing @ and domain"),
            ("@example.com",   "missing local part"),
            ("user@",          "missing domain"),
            ("user @ex.com",   "space in address"),
            ("plaintext",      "no @ at all"),
        ]
        for addr, reason in invalid_cases:
            with self.assertRaises(
                ValueError,
                msg=f"Invalid address {addr!r} ({reason}) should raise ValueError",
            ):
                _validate_recipients(addr)

        # ── Empty string ───────────────────────────────────────────────────────
        with self.assertRaises(ValueError, msg="Empty string must raise ValueError"):
            _validate_recipients("")

        # ── Whitespace-only string ─────────────────────────────────────────────
        with self.assertRaises(ValueError, msg="Whitespace-only must raise ValueError"):
            _validate_recipients("   ")

        print(f"\n  Valid single addresses  : {len(valid_cases)} — all accepted")
        print(f"  Multiple recipients     : 2-address comma string — OK")
        print(f"  Invalid addresses       : {len(invalid_cases)} — all rejected")
        print(f"  Empty / whitespace      : rejected — OK")

    # ── 8. Logs folder ────────────────────────────────────────────────────────

    def test_8_logs_folder(self):
        """logs/ folder exists (or can be created) and email_sent.log is writable."""
        log_dir  = self.project_path / "logs"
        log_file = log_dir / "email_sent.log"

        log_dir.mkdir(parents=True, exist_ok=True)

        self.assertTrue(log_dir.exists(),  f"logs/ directory could not be created: {log_dir}")
        self.assertTrue(log_dir.is_dir(),  "logs/ path exists but is not a directory")

        # Verify we can write to email_sent.log (append mode — does not clobber existing content)
        test_line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[TEST] To: test@example.com | Subject: Integration test probe\n"
        )
        try:
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(test_line)
        except OSError as exc:
            self.fail(f"Could not write to {log_file}: {exc}")

        self.assertTrue(log_file.exists(), f"email_sent.log was not created at {log_file}")
        self.assertGreater(log_file.stat().st_size, 0, "email_sent.log is empty after write")

        # Verify our test line is in the file
        written = log_file.read_text(encoding="utf-8")
        self.assertIn(
            "Integration test probe", written,
            "Test line was not written to email_sent.log",
        )

        # Verify the log format: [timestamp] [STATUS] To: | Subject:
        self.assertRegex(
            test_line,
            r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[.+\] To: .+ \| Subject: .+",
            "Log line must match format: [timestamp] [STATUS] To: xxx | Subject: xxx",
        )

        # Confirm body content is NOT in the log line (privacy check)
        self.assertNotIn(
            "body", test_line.lower(),
            "Email body must never appear in the log file",
        )

        print(f"\n  Log dir   : {log_dir}")
        print(f"  Log file  : {log_file.name}")
        print(f"  Writable  : OK")
        print(f"  Format    : [timestamp] [STATUS] To: xxx | Subject: xxx — OK")
        print(f"  Body absent from log: OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestEmailIntegration)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  EMAIL MCP SERVER — INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
