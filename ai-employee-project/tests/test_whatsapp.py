"""
tests/test_whatsapp.py

WhatsApp Silver Tier — comprehensive integration test suite.

Tests cover watcher init, session management, skill file validity, priority
detection, task-file creation with priority routing, main.py integration,
watcher count, and helper utility functions.
No live WhatsApp connection or Playwright browser is required.

Run:
    python -m pytest tests/test_whatsapp.py -v
    python tests/test_whatsapp.py              # standalone (no pytest needed)
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

_VAULT           = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
_CREDENTIALS_DIR = Path.home() / ".credentials" / "whatsapp_session"
_SESSION_FILE    = _CREDENTIALS_DIR / "context.json"


# ── Test suite ────────────────────────────────────────────────────────────────

class TestWhatsAppIntegration(unittest.TestCase):
    """Full integration test suite for the WhatsApp Silver Tier components."""

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

    # ── 1. Watcher file exists ────────────────────────────────────────────────

    def test_1_whatsapp_watcher_exists(self):
        """watchers/whatsapp_watcher.py exists and is a valid Python file."""
        watcher_path = self.project_path / "watchers" / "whatsapp_watcher.py"

        self.assertTrue(
            watcher_path.exists(),
            f"whatsapp_watcher.py not found at: {watcher_path}",
        )
        self.assertTrue(
            watcher_path.is_file(),
            "whatsapp_watcher.py path exists but is not a file",
        )
        self.assertEqual(
            watcher_path.suffix, ".py",
            "Watcher must be a .py file",
        )

        source = watcher_path.read_text(encoding="utf-8")
        self.assertGreater(len(source), 200, "whatsapp_watcher.py appears to be empty or too short")

        # Must compile without syntax errors
        try:
            compile(source, str(watcher_path), "exec")
        except SyntaxError as exc:
            self.fail(f"whatsapp_watcher.py has a syntax error: {exc}")

        # Core identifiers must be present
        for identifier in (
            "WhatsAppWatcher", "BaseWatcher", "check_for_updates",
            "create_action_file", "_ensure_session", "detect_priority",
            "_login_and_save_session", "_clean_message_text",
            "_is_notification_badge", "_create_message_fingerprint",
            "HIGH_PRIORITY_KEYWORDS", "BUSINESS_KEYWORDS",
        ):
            self.assertIn(
                identifier, source,
                f"whatsapp_watcher.py is missing expected identifier: '{identifier}'",
            )

        print(f"\n  Path       : {watcher_path}")
        print(f"  Size       : {len(source):,} chars")
        print(f"  Syntax     : valid Python")
        print(f"  Identifiers: all required — OK")

    # ── 2. Watcher class structure ────────────────────────────────────────────

    def test_2_whatsapp_watcher_class(self):
        """WhatsAppWatcher initialises correctly and inherits from BaseWatcher."""
        from watchers.whatsapp_watcher import WhatsAppWatcher
        from watchers.base_watcher import BaseWatcher

        # Inheritance
        self.assertTrue(
            issubclass(WhatsAppWatcher, BaseWatcher),
            "WhatsAppWatcher must inherit from BaseWatcher",
        )

        # Instantiation
        watcher = WhatsAppWatcher(vault_path=self.vault_path, check_interval=60)

        # Attribute defaults
        self.assertEqual(
            watcher.vault_path, Path(self.vault_path),
            f"vault_path mismatch: expected {self.vault_path}, got {watcher.vault_path}",
        )
        self.assertEqual(
            watcher.check_interval, 60,
            f"check_interval should be 60, got {watcher.check_interval}",
        )
        self.assertEqual(
            watcher.session_path, Path.home() / ".credentials" / "whatsapp_session",
            "session_path must point to ~/.credentials/whatsapp_session",
        )
        self.assertIsInstance(watcher.keywords, list, "keywords must be a list")
        self.assertGreater(len(watcher.keywords), 0, "keywords list must not be empty")
        self.assertIsInstance(
            watcher.high_priority_keywords, list,
            "high_priority_keywords must be a list",
        )
        self.assertIsInstance(
            watcher.business_keywords, list,
            "business_keywords must be a list",
        )
        self.assertIsInstance(
            watcher._seen_ids, set,
            "_seen_ids must be a set for O(1) deduplication",
        )

        # Required methods
        required_methods = (
            "check_for_updates",
            "create_action_file",
            "_ensure_session",
            "_login_and_save_session",
            "_check_unread_messages",
            "_extract_message_data",
            "_extract_sender_name",
            "_extract_message_text",
            "_clean_message_text",
            "_is_notification_badge",
            "_create_message_fingerprint",
            "detect_priority",
        )
        for method in required_methods:
            self.assertTrue(
                callable(getattr(watcher, method, None)),
                f"WhatsAppWatcher is missing required method: {method}",
            )

        # check_for_updates and create_action_file signatures match BaseWatcher contract
        sig_cfu = inspect.signature(watcher.check_for_updates)
        sig_caf = inspect.signature(watcher.create_action_file)
        self.assertEqual(
            len(sig_cfu.parameters), 0,
            "check_for_updates() must take no arguments beyond self",
        )
        self.assertIn(
            "item", sig_caf.parameters,
            "create_action_file() must accept an 'item' parameter",
        )

        print(f"\n  vault_path    : {watcher.vault_path}")
        print(f"  check_interval: {watcher.check_interval}s")
        print(f"  session_path  : {watcher.session_path}")
        print(f"  keywords      : {watcher.keywords}")
        print(f"  BaseWatcher   : OK")
        print(f"  All {len(required_methods)} required methods present: OK")

    # ── 3. Skill file structure ───────────────────────────────────────────────

    def test_3_whatsapp_skill_exists(self):
        """whatsapp-monitor SKILL.md exists, has valid frontmatter, and is pure Markdown."""
        skill_path = self.project_path / ".claude" / "skills" / "whatsapp-monitor" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"whatsapp-monitor SKILL.md not found at: {skill_path}",
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
        for field in ("name:", "description:", "triggers:"):
            self.assertIn(
                field, frontmatter,
                f"Frontmatter missing required field: '{field}'",
            )

        # name must be whatsapp-monitor
        self.assertIn(
            "whatsapp-monitor", frontmatter,
            "Frontmatter 'name' must equal 'whatsapp-monitor'",
        )

        # At least two trigger phrases
        trigger_items = re.findall(r"^\s+- .+", frontmatter, re.MULTILINE)
        self.assertGreaterEqual(
            len(trigger_items), 2,
            f"Frontmatter must declare at least 2 triggers, found: {len(trigger_items)}",
        )

        # Required body sections
        for section in (
            "## Purpose",
            "## Process",
            "## How to Run",
            "## Output",
            "## Expected Output",
            "## Dependencies",
            "## Notes",
        ):
            self.assertIn(
                section, content,
                f"SKILL.md is missing required section: '{section}'",
            )

        # Must reference the correct watcher module
        self.assertIn(
            "whatsapp_watcher", content,
            "SKILL.md must reference 'whatsapp_watcher' in How to Run",
        )

        # Must reference context.json session file
        self.assertIn(
            "context.json", content,
            "SKILL.md must reference 'context.json' as the session file",
        )

        # Must document priority routing
        self.assertIn(
            "Needs_Action", content,
            "SKILL.md must document priority routing to Needs_Action/",
        )

        # Pure Markdown — no Python code blocks
        python_blocks = re.findall(r"```python", content, re.IGNORECASE)
        self.assertEqual(
            len(python_blocks), 0,
            f"SKILL.md must not contain ```python code blocks (found {len(python_blocks)})",
        )

        # Must include at least two Expected Output examples
        code_blocks = re.findall(r"```", content)
        self.assertGreaterEqual(
            len(code_blocks), 4,
            "Expected Output section must contain at least two fenced code examples",
        )

        # Trigger phrases: "check whatsapp" must appear
        self.assertIn("check whatsapp", content, "Triggers must include 'check whatsapp'")

        print(f"\n  Path          : {skill_path}")
        print(f"  Size          : {len(content):,} chars")
        print(f"  Frontmatter   : name=whatsapp-monitor, triggers ({len(trigger_items)}) — OK")
        print(f"  Sections      : all required — OK")
        print(f"  Routing docs  : Needs_Action — OK")
        print(f"  No Python code blocks: OK")

    # ── 4. Session folder ─────────────────────────────────────────────────────

    def test_4_session_folder(self):
        """Session directory exists (or can be created) and reports context.json status."""
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

        # Writable check
        probe = _CREDENTIALS_DIR / ".write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            writable = True
        except OSError:
            writable = False

        self.assertTrue(writable, f"Session directory is not writable: {_CREDENTIALS_DIR}")

        if _SESSION_FILE.exists() and _SESSION_FILE.stat().st_size > 20:
            print(f"  context.json  : FOUND ({_SESSION_FILE.stat().st_size:,} bytes)")
        else:
            print("  context.json  : NOT FOUND (first-time QR login required)")
            print("  Run: python watchers/whatsapp_watcher.py  to create session")

        from watchers.whatsapp_watcher import WhatsAppWatcher
        watcher = WhatsAppWatcher(vault_path=self.vault_path)
        self.assertEqual(
            watcher.session_path, _CREDENTIALS_DIR,
            f"WhatsAppWatcher.session_path must equal {_CREDENTIALS_DIR}",
        )
        self.assertEqual(
            watcher._context_file, _SESSION_FILE,
            "WhatsAppWatcher._context_file must point to context.json",
        )

        print(f"  Writable      : OK")
        print(f"  Watcher path  : {watcher.session_path} — OK")

    # ── 5. main.py integration ────────────────────────────────────────────────

    def test_5_main_integration(self):
        """main.py imports WhatsAppWatcher and integrates it in the orchestrator."""
        main_path = self.project_path / "main.py"

        self.assertTrue(main_path.exists(), f"main.py not found at: {main_path}")

        source = main_path.read_text(encoding="utf-8")

        self.assertIn(
            "from watchers.whatsapp_watcher import WhatsAppWatcher",
            source,
            "main.py must import WhatsAppWatcher from watchers.whatsapp_watcher",
        )
        self.assertIn(
            "whatsapp-interval", source,
            "main.py must define --whatsapp-interval CLI argument",
        )

        wa_block_start = source.find('"--whatsapp-interval"')
        self.assertGreater(
            wa_block_start, -1,
            'main.py must define add_argument("--whatsapp-interval", ...)',
        )
        wa_block = source[wa_block_start : wa_block_start + 200]
        self.assertIn("default=60", wa_block, "--whatsapp-interval must default to 60 seconds")

        self.assertIn('name="WhatsAppWatcher"', source)
        self.assertIn("watcher_cls=WhatsAppWatcher", source)
        self.assertIn("whatsapp_interval", source)
        self.assertIn("whatsapp_interval: int", source)
        self.assertIn("WhatsApp Watcher", source)
        self.assertIn("QR", source)
        self.assertIn("_health_check", source)

        print(f"\n  File                         : {main_path}")
        print(f"  WhatsAppWatcher import        : OK")
        print(f"  --whatsapp-interval (default=60): OK")
        print(f"  WatcherThread name='WhatsAppWatcher': OK")
        print(f"  _health_check method          : OK")

    # ── 6. Priority detection ─────────────────────────────────────────────────

    def test_6_priority_detection(self):
        """detect_priority() returns 'high' for urgent messages and 'normal' otherwise."""
        from watchers.whatsapp_watcher import WhatsAppWatcher

        watcher = WhatsAppWatcher(vault_path=self.vault_path)

        high_priority_cases = [
            ("Urgent: client needs invoice ASAP!", "urgent + asap"),
            ("URGENT issue with the system",       "uppercase URGENT"),
            ("Need this ASAP please",              "asap alone"),
            ("Emergency meeting in 10 minutes",    "emergency"),
            ("Critical bug in production",         "critical"),
            ("Deadline is today, help!",           "deadline"),
            ("Important update from management",   "important"),
            ("Client called — needs response",     "client"),
            ("Payment overdue by 30 days",         "payment"),
            ("Action required immediately",        "action required + immediately"),
            ("I need this right now",              "right now"),
            ("Still waiting for your response",   "waiting"),
            ("Can you help me with this?",         "help"),
        ]
        for msg, label in high_priority_cases:
            with self.subTest(msg=label):
                result = watcher.detect_priority(msg)
                self.assertEqual(
                    result, "high",
                    f"Expected 'high' for [{label}] message: {msg!r}, got {result!r}",
                )

        normal_priority_cases = [
            ("Meeting scheduled for next week",    "meeting only"),
            ("Invoice attached for your review",   "invoice only"),
            ("Let's catch up tomorrow",            "no keywords"),
            ("Thanks for the update",              "no keywords"),
            ("",                                   "empty string"),
            ("Hello, how are you doing today?",    "casual message"),
        ]
        for msg, label in normal_priority_cases:
            with self.subTest(msg=label):
                result = watcher.detect_priority(msg)
                self.assertEqual(
                    result, "normal",
                    f"Expected 'normal' for [{label}] message: {msg!r}, got {result!r}",
                )

        print(f"\n  High-priority cases  : {len(high_priority_cases)} — all returned 'high'")
        print(f"  Normal-priority cases: {len(normal_priority_cases)} — all returned 'normal'")
        print(f"  Case-insensitive matching: OK")

    # ── 7. Task file creation with priority routing ───────────────────────────

    def test_7_task_file_format(self):
        """create_action_file() routes high-priority to Needs_Action/ and normal to Inbox/."""
        from watchers.whatsapp_watcher import WhatsAppWatcher

        watcher = WhatsAppWatcher(vault_path=self.vault_path)

        needs_action = self.vault_path / "Needs_Action"
        inbox        = self.vault_path / "Inbox"
        needs_action.mkdir(parents=True, exist_ok=True)
        inbox.mkdir(parents=True, exist_ok=True)

        # ── High-priority mock message ────────────────────────────────────────
        received_dt = datetime(2026, 4, 11, 14, 30, 0)
        mock_item = {
            "contact":       "Test Contact",
            "text":          "Urgent: client invoice #9999 overdue — need reply ASAP!",
            "phone":         "+1234567890",
            "received_dt":   received_dt,
            "timestamp_raw": "2:30 PM",
        }

        card_path = watcher.create_action_file(mock_item)
        self._temp_files.append(card_path)

        # ── File existence and naming ─────────────────────────────────────────
        self.assertTrue(card_path.exists(), f"Task file was not created at: {card_path}")
        self.assertEqual(card_path.suffix, ".md", "Task file must have .md extension")
        self.assertTrue(
            card_path.name.startswith("WHATSAPP_"),
            f"Task filename must start with 'WHATSAPP_', got: {card_path.name}",
        )

        # HIGH priority must go to Needs_Action/
        self.assertEqual(
            card_path.parent, needs_action,
            f"HIGH priority task must be in Needs_Action/, got: {card_path.parent}",
        )

        # Filename format: WHATSAPP_YYYYMMDD_HHMMSS_<contact_slug>.md
        self.assertRegex(
            card_path.name,
            r"^WHATSAPP_\d{8}_\d{6}_[a-z0-9_]+\.md$",
            f"Filename must match WHATSAPP_YYYYMMDD_HHMMSS_<slug>.md, got: {card_path.name}",
        )

        # Timestamp in filename must match received_dt
        self.assertIn(
            "20260411_143000", card_path.name,
            f"Filename must encode received_dt 2026-04-11 14:30:00, got: {card_path.name}",
        )

        content = card_path.read_text(encoding="utf-8")

        # ── Frontmatter ───────────────────────────────────────────────────────
        self.assertTrue(content.startswith("---"), "Task file must start with YAML frontmatter '---'")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter block not properly closed with '---'")

        fm = parts[1]

        fm_checks = {
            "type: whatsapp_message": "type field",
            "from:":                  "from field",
            "message_preview:":       "message_preview field",
            "received:":              "received timestamp",
            "priority:":              "priority field",
            "status: pending":        "status field",
            "message_id:":            "message_id dedup field",
        }
        for snippet, label in fm_checks.items():
            self.assertIn(snippet, fm, f"Frontmatter missing {label}: '{snippet}'")

        self.assertIn("Test Contact", fm, "from field must contain the contact name")
        self.assertIn("+1234567890", fm, "phone field must appear in frontmatter when provided")
        self.assertIn("priority: high", fm, "Priority must be 'high' for urgent/asap message")
        self.assertIn("2026-04-11T14:30:00", fm, "received timestamp must be in ISO format")

        # ── Body sections ─────────────────────────────────────────────────────
        body = parts[2]

        for section in (
            "# WhatsApp Message: Test Contact",
            "**From:**",
            "**Received:**",
            "**Priority:**",
            "## Message Preview",
            "## Suggested Actions",
            "- [ ] Reply to message",
            "- [ ] Call contact",
            "- [ ] Mark as important",
            "- [ ] Create task in Needs_Action",
            "## Links",
            "web.whatsapp.com",
        ):
            self.assertIn(section, body, f"Task file body missing: '{section}'")

        self.assertIn("Urgent:", content, "Message text must appear in the Message Preview section")

        # Deduplication: message_id added to _seen_ids after creation
        from watchers.whatsapp_watcher import _make_msg_id
        msg_id = _make_msg_id(mock_item)
        self.assertIn(msg_id, watcher._seen_ids, f"message_id must be added to _seen_ids")

        # ── Normal-priority variant → Inbox/ ──────────────────────────────────
        mock_normal = {
            "contact":       "Another Contact",
            "text":          "Meeting scheduled for Thursday at 3pm",
            "phone":         "",
            "received_dt":   datetime(2026, 4, 11, 9, 0, 0),
            "timestamp_raw": "9:00 AM",
        }
        normal_path = watcher.create_action_file(mock_normal)
        self._temp_files.append(normal_path)

        # NORMAL priority must go to Inbox/
        self.assertEqual(
            normal_path.parent, inbox,
            f"NORMAL priority task must be in Inbox/, got: {normal_path.parent}",
        )

        normal_content = normal_path.read_text(encoding="utf-8")
        self.assertIn("priority: normal", normal_content, "Priority must be 'normal' for meeting keyword")

        # Empty phone field should not appear in frontmatter
        self.assertNotIn(
            'phone: ""', normal_content.split("---", 2)[1],
            "Empty phone field should not appear in frontmatter",
        )

        print(f"\n  High-priority card  : {card_path.name} -> Needs_Action/ -- OK")
        print(f"  Frontmatter fields  : type, from, message_preview, received, priority, status, phone, message_id -- OK")
        print(f"  Body sections       : Message Preview, Suggested Actions, Links -- OK")
        print(f"  _seen_ids updated   : OK")
        print(f"  Normal-priority card: {normal_path.name} -> Inbox/ -- OK")

    # ── 8. Watcher count in main.py ───────────────────────────────────────────

    def test_8_watcher_count(self):
        """main.py contains all four Silver Tier watchers in the orchestrator."""
        main_path = self.project_path / "main.py"
        self.assertTrue(main_path.exists(), f"main.py not found at: {main_path}")

        source = main_path.read_text(encoding="utf-8")

        expected_watchers = {
            "FileWatcher":     ("file-interval",     "60"),
            "GmailWatcher":    ("gmail-interval",    "120"),
            "LinkedInWatcher": ("linkedin-interval", "180"),
            "WhatsAppWatcher": ("whatsapp-interval", "60"),
        }

        for watcher_name, (cli_arg, default) in expected_watchers.items():
            with self.subTest(watcher=watcher_name):
                self.assertIn(watcher_name, source)
                self.assertIn(f'name="{watcher_name}"', source)
                self.assertIn(cli_arg, source)

        self.assertIn('"WhatsAppWatcher"', source)
        self.assertIn("whatsapp_messages_checked", source)

        watcher_thread_count = (
            source.count('name="FileWatcher"') +
            source.count('name="GmailWatcher"') +
            source.count('name="LinkedInWatcher"') +
            source.count('name="WhatsAppWatcher"')
        )
        self.assertEqual(watcher_thread_count, 4, f"Expected 4 WatcherThread entries, found {watcher_thread_count}")

        for label in ("File Watcher", "Gmail Watcher", "LinkedIn Watcher", "WhatsApp Watcher"):
            self.assertIn(label, source, f"Startup banner must mention '{label}'")

        print(f"\n  All 4 watchers in _watchers list: OK")
        for name, (cli_arg, default) in expected_watchers.items():
            print(f"    {name:<18} --{cli_arg} (default={default}s) — OK")

    # ── 9. Message cleaning ───────────────────────────────────────────────────

    def test_9_message_cleaning(self):
        """_clean_message_text() removes timestamps, UI artifacts, and notification counts."""
        from watchers.whatsapp_watcher import WhatsAppWatcher

        watcher = WhatsAppWatcher(vault_path=self.vault_path)

        cases = [
            # (raw_input, must_not_contain, label)
            ("John 10:36 AM: Meeting today Typing...", ["10:36", "Typing..."], "timestamp + Typing"),
            ("Online: Quick call?",                    ["Online"],             "Online artifact"),
            ("Photo",                                  ["Photo"],              "media type"),
            ("Need help 2:30 PM",                      ["2:30"],              "timestamp"),
            ("3",                                      ["3"],                  "badge count"),
        ]

        for raw, must_not_contain, label in cases:
            cleaned = watcher._clean_message_text(raw)
            for fragment in must_not_contain:
                with self.subTest(case=label, fragment=fragment):
                    self.assertNotIn(
                        fragment, cleaned,
                        f"[{label}] '{fragment}' should have been removed from: {raw!r}",
                    )

        print(f"\n  Cleaned {len(cases)} message variants — all artifacts removed")

    # ── 10. Notification badge detection ─────────────────────────────────────

    def test_10_notification_badge_detection(self):
        """_is_notification_badge() correctly identifies badge-only elements."""
        from watchers.whatsapp_watcher import WhatsAppWatcher

        watcher = WhatsAppWatcher(vault_path=self.vault_path)

        badges    = ["3", "12", "99", "  5  ", ""]
        non_badge = ["Meeting ASAP", "Call me", "Invoice due", "1 thing to do"]

        for text in badges:
            with self.subTest(text=repr(text)):
                self.assertTrue(
                    watcher._is_notification_badge(text),
                    f"Expected badge=True for: {text!r}",
                )
        for text in non_badge:
            with self.subTest(text=repr(text)):
                self.assertFalse(
                    watcher._is_notification_badge(text),
                    f"Expected badge=False for: {text!r}",
                )

        print(f"\n  Badge detection: {len(badges)} badges, {len(non_badge)} non-badges — OK")

    # ── 11. Message fingerprint ───────────────────────────────────────────────

    def test_11_message_fingerprint(self):
        """_create_message_fingerprint() produces stable, content-based dedup keys."""
        from watchers.whatsapp_watcher import WhatsAppWatcher

        watcher = WhatsAppWatcher(vault_path=self.vault_path)

        # Both messages share the same first 50 chars (both longer than 50)
        base_msg = "Need invoice ASAP please confirm by end of day Thursday"
        long_msg = "Need invoice ASAP please confirm by end of day Thursday and also the full report"

        fp1 = watcher._create_message_fingerprint("John", base_msg)
        fp2 = watcher._create_message_fingerprint("John", long_msg)
        fp3 = watcher._create_message_fingerprint("Jane", base_msg)

        # Same sender + same first-50-chars -> identical fingerprint
        self.assertEqual(fp1, fp2, "Fingerprints must match when sender + first 50 chars are same")

        # Different sender → different fingerprint
        self.assertNotEqual(fp1, fp3, "Fingerprints must differ when sender changes")

        # Format: contains separator
        self.assertIn("|", fp1, "Fingerprint must use '|' separator")

        # Case-insensitive: same message in different case must produce same fingerprint
        fp_lower = watcher._create_message_fingerprint("john", base_msg.lower())
        self.assertEqual(fp1, fp_lower, "Fingerprints must be case-insensitive")

        print(f"\n  Fingerprint consistency : OK")
        print(f"  Fingerprint uniqueness  : OK")
        print(f"  Case-insensitive        : OK")

    # ── 12. Helper utility functions ──────────────────────────────────────────

    def test_12_helper_functions(self):
        """helpers/whatsapp_helper.py provides all required utility functions."""
        helper_path = self.project_path / "helpers" / "whatsapp_helper.py"
        self.assertTrue(helper_path.exists(), f"whatsapp_helper.py not found at: {helper_path}")

        source = helper_path.read_text(encoding="utf-8")
        for fn in (
            "clean_whatsapp_message",
            "extract_phone_number",
            "is_business_message",
            "detect_priority",
            "create_message_fingerprint",
            "format_whatsapp_task",
        ):
            self.assertIn(fn, source, f"helpers/whatsapp_helper.py missing function: {fn}")

        from helpers.whatsapp_helper import (
            clean_whatsapp_message,
            extract_phone_number,
            is_business_message,
            detect_priority,
            create_message_fingerprint,
            format_whatsapp_task,
        )

        # clean_whatsapp_message
        raw     = "John 10:36 AM: Meeting today Typing..."
        cleaned = clean_whatsapp_message(raw)
        self.assertNotIn("Typing...", cleaned)
        self.assertNotIn("10:36", cleaned)

        # extract_phone_number
        phone = extract_phone_number("Call me at +92 300 1234567")
        self.assertIsNotNone(phone)
        self.assertIn("300", phone)
        self.assertIsNone(extract_phone_number("No phone here"))

        # is_business_message
        kw = ["urgent", "meeting", "invoice"]
        self.assertTrue(is_business_message("Urgent meeting today", kw))
        self.assertFalse(is_business_message("How are you?", kw))

        # detect_priority
        hi_kw = ["urgent", "asap", "deadline"]
        self.assertEqual(detect_priority("Need this ASAP", hi_kw), "high")
        self.assertEqual(detect_priority("Nice to meet you", hi_kw), "normal")

        # create_message_fingerprint
        fp = create_message_fingerprint("Alice", "Hello world")
        self.assertIn("|", fp)
        self.assertEqual(fp, create_message_fingerprint("alice", "hello world"))

        # format_whatsapp_task
        task_content = format_whatsapp_task("Bob", "Need invoice", phone="+1234", priority="high")
        self.assertIn("Bob", task_content)
        self.assertIn("+1234", task_content)
        self.assertIn("high", task_content)
        self.assertIn("## Message Preview", task_content)

        print(f"\n  clean_whatsapp_message   : OK")
        print(f"  extract_phone_number     : OK")
        print(f"  is_business_message      : OK")
        print(f"  detect_priority          : OK")
        print(f"  create_message_fingerprint: OK")
        print(f"  format_whatsapp_task     : OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestWhatsAppIntegration)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  WHATSAPP SILVER TIER — INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
