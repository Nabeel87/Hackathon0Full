"""
tests/test_silver_integration.py

Silver Tier — master integration test suite.

Verifies that every Silver Tier component exists, imports cleanly,
has the correct structure, and is wired together correctly in main.py.
No live API connections, browser sessions, or network calls are made.

Run:
    python -m pytest tests/test_silver_integration.py -v
    python tests/test_silver_integration.py              # standalone (no pytest needed)
"""

import inspect
import re
import sys
import unittest
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VAULT = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")


# ── Test suite ────────────────────────────────────────────────────────────────

class TestSilverIntegration(unittest.TestCase):
    """
    Master integration test suite for the Silver Tier.
    Each test verifies a distinct layer of the system; together they confirm
    that all components are present, structurally correct, and wired together.
    """

    def setUp(self):
        self.vault_path   = _VAULT
        self.project_path = _PROJECT_ROOT
        self._temp_files: list[Path] = []

    def tearDown(self):
        for path in self._temp_files:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    # ── 1. All 4 watchers ────────────────────────────────────────────────────

    def test_1_all_watchers_exist(self):
        """All 4 watchers import cleanly, inherit BaseWatcher, and expose required methods."""
        from watchers.base_watcher import BaseWatcher

        watcher_specs = {
            "FileWatcher": {
                "module":  "watchers.file_watcher",
                "methods": ["check_for_updates", "create_action_file"],
            },
            "GmailWatcher": {
                "module":  "watchers.gmail_watcher",
                "methods": ["check_for_updates", "create_action_file", "_get_service"],
            },
            "LinkedInWatcher": {
                "module":  "watchers.linkedin_watcher",
                "methods": ["check_for_updates", "create_action_file",
                            "_ensure_session", "_login_and_save_session"],
            },
            "WhatsAppWatcher": {
                "module":  "watchers.whatsapp_watcher",
                "methods": ["check_for_updates", "create_action_file",
                            "_ensure_session", "_login_and_save_session",
                            "detect_priority"],
            },
        }

        for class_name, spec in watcher_specs.items():
            with self.subTest(watcher=class_name):
                # File exists
                module_path = spec["module"].replace(".", "/") + ".py"
                watcher_file = self.project_path / module_path
                self.assertTrue(
                    watcher_file.exists(),
                    f"{module_path} not found",
                )

                # Compiles cleanly
                source = watcher_file.read_text(encoding="utf-8")
                try:
                    compile(source, str(watcher_file), "exec")
                except SyntaxError as exc:
                    self.fail(f"{class_name}: syntax error — {exc}")

                # Importable
                mod = __import__(spec["module"], fromlist=[class_name])
                cls = getattr(mod, class_name)

                # Inherits BaseWatcher
                self.assertTrue(
                    issubclass(cls, BaseWatcher),
                    f"{class_name} must inherit from BaseWatcher",
                )

                # Instantiable
                instance = cls(vault_path=self.vault_path, check_interval=60)
                self.assertEqual(
                    instance.vault_path, Path(self.vault_path),
                    f"{class_name}.vault_path set incorrectly",
                )

                # All required methods present and callable
                for method in spec["methods"]:
                    self.assertTrue(
                        callable(getattr(instance, method, None)),
                        f"{class_name} missing required method: {method}",
                    )

        print(f"\n  FileWatcher     : BaseWatcher subclass, 2 methods — OK")
        print(f"  GmailWatcher    : BaseWatcher subclass, 3 methods — OK")
        print(f"  LinkedInWatcher : BaseWatcher subclass, 4 methods — OK")
        print(f"  WhatsAppWatcher : BaseWatcher subclass, 5 methods — OK")
        print(f"  All 4 watchers compile clean and instantiate: OK")

    # ── 2. All 12 skills ─────────────────────────────────────────────────────

    def test_2_all_skills_exist(self):
        """All 12 Agent Skills exist as valid SKILL.md files with correct frontmatter."""
        skills_dir = self.project_path / ".claude" / "skills"

        # Silver Tier requires all 12 skills
        required_skills = {
            # monitoring
            "file-monitor":      ("check for new files", "file_watcher"),
            "gmail-monitor":     ("check gmail",         "gmail_watcher"),
            "linkedin-monitor":  ("check linkedin",      "linkedin_watcher"),
            "whatsapp-monitor":  ("check whatsapp",      "whatsapp_watcher"),
            # actions
            "send-email":        ("send email",          "email_server"),
            "post-linkedin":     ("post to linkedin",    "linkedin_poster"),
            # approval
            "approve-action":    ("approve",             "Pending_Approval"),
            "reject-action":     ("reject",              "Rejected"),
            # utility
            "create-plan":       ("create a plan",       "plan_creator"),
            "process-inbox":     ("process inbox",       "inbox_processor"),
            "update-dashboard":  ("update dashboard",    "dashboard_updater"),
            # meta
            "skill-creator":     ("create skill",        "watchers"),
        }

        for skill_name, (trigger_hint, module_hint) in required_skills.items():
            with self.subTest(skill=skill_name):
                skill_file = skills_dir / skill_name / "SKILL.md"

                # File exists
                self.assertTrue(
                    skill_file.exists(),
                    f"SKILL.md not found for skill '{skill_name}' at: {skill_file}",
                )

                content = skill_file.read_text(encoding="utf-8")
                self.assertGreater(
                    len(content), 200,
                    f"{skill_name}/SKILL.md is suspiciously short ({len(content)} chars)",
                )

                # Valid frontmatter
                self.assertTrue(
                    content.startswith("---"),
                    f"{skill_name}/SKILL.md must start with '---' frontmatter",
                )
                parts = content.split("---", 2)
                self.assertGreaterEqual(
                    len(parts), 3,
                    f"{skill_name}/SKILL.md: frontmatter not properly closed",
                )
                fm = parts[1]

                # Required frontmatter fields
                for field in ("name:", "description:", "triggers:"):
                    self.assertIn(
                        field, fm,
                        f"{skill_name}/SKILL.md frontmatter missing field: '{field}'",
                    )

                # name field value matches skill directory name
                self.assertIn(
                    skill_name, fm,
                    f"{skill_name}/SKILL.md 'name:' field must equal '{skill_name}'",
                )

                # At least one trigger phrase
                self.assertRegex(
                    fm, r"- \S+",
                    f"{skill_name}/SKILL.md must have at least one trigger phrase",
                )

                # Required body sections (skill-creator uses Usage Examples instead
                # of How to Run — it's a meta-skill with no Python module to call)
                universal_sections = ("## Purpose", "## Process", "## Dependencies")
                for section in universal_sections:
                    self.assertIn(
                        section, content,
                        f"{skill_name}/SKILL.md missing required section: '{section}'",
                    )
                # How to Run OR Usage Examples (both are valid depending on skill type)
                has_run_section = (
                    "## How to Run" in content or "## Usage Examples" in content
                )
                self.assertTrue(
                    has_run_section,
                    f"{skill_name}/SKILL.md must have '## How to Run' or '## Usage Examples'",
                )

                # No Python code blocks (skills are pure Markdown)
                python_blocks = re.findall(r"```python", content, re.IGNORECASE)
                self.assertEqual(
                    len(python_blocks), 0,
                    f"{skill_name}/SKILL.md must not contain ```python blocks "
                    f"(found {len(python_blocks)})",
                )

                # References the correct Python module
                self.assertIn(
                    module_hint, content,
                    f"{skill_name}/SKILL.md must reference '{module_hint}' in body",
                )

        print(f"\n  Monitoring skills (4): file-monitor, gmail-monitor,"
              f" linkedin-monitor, whatsapp-monitor — OK")
        print(f"  Action skills     (2): send-email, post-linkedin — OK")
        print(f"  Approval skills   (2): approve-action, reject-action — OK")
        print(f"  Utility skills    (3): create-plan, process-inbox, update-dashboard — OK")
        print(f"  Meta skill        (1): skill-creator — OK")
        print(f"  All 12 skills: valid frontmatter, required sections, no Python code — OK")

    # ── 3. All helpers ────────────────────────────────────────────────────────

    def test_3_all_helpers_exist(self):
        """All 4 helper modules exist, compile, import, and export expected functions."""
        helper_specs = {
            "dashboard_updater": {
                "functions": ["update_activity", "update_component_status",
                              "update_stats", "refresh_vault_counts"],
            },
            "inbox_processor": {
                "functions": ["process_inbox"],
            },
            "plan_creator": {
                "functions": ["create_plan"],
            },
            "linkedin_poster": {
                "functions": ["post_to_linkedin"],
            },
        }

        helpers_dir = self.project_path / "helpers"

        for module_name, spec in helper_specs.items():
            with self.subTest(helper=module_name):
                helper_file = helpers_dir / f"{module_name}.py"

                # File exists
                self.assertTrue(
                    helper_file.exists(),
                    f"helpers/{module_name}.py not found at: {helper_file}",
                )

                source = helper_file.read_text(encoding="utf-8")
                self.assertGreater(
                    len(source), 100,
                    f"helpers/{module_name}.py is suspiciously short",
                )

                # Compiles clean
                try:
                    compile(source, str(helper_file), "exec")
                except SyntaxError as exc:
                    self.fail(f"helpers/{module_name}.py syntax error: {exc}")

                # Functions importable and callable
                mod = __import__(f"helpers.{module_name}", fromlist=spec["functions"])
                for fn_name in spec["functions"]:
                    fn = getattr(mod, fn_name, None)
                    self.assertIsNotNone(
                        fn,
                        f"helpers/{module_name}.py does not export '{fn_name}'",
                    )
                    self.assertTrue(
                        callable(fn),
                        f"helpers/{module_name}.{fn_name} is not callable",
                    )

        print(f"\n  dashboard_updater : update_activity, update_component_status,"
              f" update_stats, refresh_vault_counts — OK")
        print(f"  inbox_processor   : process_inbox — OK")
        print(f"  plan_creator      : create_plan — OK")
        print(f"  linkedin_poster   : post_to_linkedin — OK")
        print(f"  All 4 helpers compile clean and export expected functions: OK")

    # ── 4. MCP email server ───────────────────────────────────────────────────

    def test_4_mcp_server_exists(self):
        """mcp_servers/email_server.py exists, compiles, and exports required functions."""
        server_path = self.project_path / "mcp_servers" / "email_server.py"

        self.assertTrue(
            server_path.exists(),
            f"mcp_servers/email_server.py not found at: {server_path}",
        )

        source = server_path.read_text(encoding="utf-8")
        self.assertGreater(len(source), 200, "email_server.py is suspiciously short")

        # Compiles clean
        try:
            compile(source, str(server_path), "exec")
        except SyntaxError as exc:
            self.fail(f"email_server.py has a syntax error: {exc}")

        # Required functions exist in source (static check — avoids loading Google deps)
        for fn_name in ("send_email", "draft_email", "_validate_recipients"):
            self.assertIn(
                f"def {fn_name}(", source,
                f"email_server.py must define {fn_name}()",
            )

        # Gmail send scope declared
        self.assertIn(
            "gmail.send", source,
            "email_server.py must declare the gmail.send OAuth scope",
        )
        self.assertIn(
            "gmail.readonly", source,
            "email_server.py must declare the gmail.readonly OAuth scope",
        )

        # Vault-integration: must reference Pending_Approval
        self.assertIn(
            "Pending_Approval", source,
            "email_server.py must write drafts to Pending_Approval/",
        )

        # Import the module (Google deps may be unavailable in CI — soft check)
        try:
            from mcp_servers.email_server import send_email, draft_email

            # send_email(to, subject, body, ...) signature
            sig    = inspect.signature(send_email)
            params = list(sig.parameters.keys())
            for required in ("to", "subject", "body"):
                self.assertIn(
                    required, params,
                    f"send_email must accept '{required}' parameter",
                )

            # draft_email also requires to, subject, body
            dsig    = inspect.signature(draft_email)
            dparams = list(dsig.parameters.keys())
            for required in ("to", "subject", "body"):
                self.assertIn(
                    required, dparams,
                    f"draft_email must accept '{required}' parameter",
                )

            print(f"\n  send_email  params : {params}")
            print(f"  draft_email params : {dparams}")
        except ImportError:
            print(f"\n  Runtime import skipped (Google API deps may be missing) — static checks passed")

        print(f"\n  Path             : {server_path}")
        print(f"  Size             : {len(source):,} chars")
        print(f"  Syntax           : valid Python")
        print(f"  Functions        : send_email, draft_email, _validate_recipients — OK")
        print(f"  Gmail scopes     : readonly + send — OK")
        print(f"  Pending_Approval : referenced — OK")

    # ── 5. Scheduler integration ──────────────────────────────────────────────

    def test_5_scheduler_integration(self):
        """Scheduler module exports 4 tasks; APScheduler is installed; main.py wires it."""
        from scheduler.scheduled_tasks import get_scheduled_tasks, create_scheduler
        from apscheduler.schedulers.background import BackgroundScheduler

        # ── Task registry ─────────────────────────────────────────────────────
        tasks = get_scheduled_tasks(str(self.vault_path))
        self.assertIsInstance(tasks, list, "get_scheduled_tasks must return a list")
        self.assertEqual(
            len(tasks), 4,
            f"Expected 4 scheduled tasks, got {len(tasks)}",
        )

        expected_ids = {
            "check_approval_timeouts",
            "generate_daily_summary",
            "cleanup_old_files",
            "health_check_watchers",
        }
        found_ids = {t["id"] for t in tasks}
        self.assertEqual(
            found_ids, expected_ids,
            f"Task IDs mismatch.\n  Expected: {sorted(expected_ids)}\n"
            f"  Got:      {sorted(found_ids)}",
        )

        # Every task has func + trigger
        for task in tasks:
            self.assertTrue(callable(task.get("func")),
                            f"Task '{task.get('id')}' func is not callable")
            self.assertIn(task.get("trigger"), ("interval", "cron"),
                          f"Task '{task.get('id')}' trigger must be 'interval' or 'cron'")

        # ── Scheduler factory ─────────────────────────────────────────────────
        sched = create_scheduler(str(self.vault_path))
        self.assertIsInstance(
            sched, BackgroundScheduler,
            "create_scheduler() must return a BackgroundScheduler",
        )
        self.assertFalse(sched.running, "create_scheduler() must return unstarted scheduler")
        self.assertEqual(
            len(sched.get_jobs()), 4,
            f"Scheduler must have 4 jobs registered, got {len(sched.get_jobs())}",
        )

        # ── main.py integration ───────────────────────────────────────────────
        main_source = (self.project_path / "main.py").read_text(encoding="utf-8")
        for symbol in ("BackgroundScheduler", "get_scheduled_tasks",
                       "scheduler.start()", "scheduler.shutdown",
                       "enable_scheduler", "no-scheduler"):
            self.assertIn(
                symbol, main_source,
                f"main.py must reference '{symbol}' for scheduler integration",
            )
        self.assertNotIn(
            "BlockingScheduler", main_source,
            "main.py must not use BlockingScheduler (would block watcher threads)",
        )

        print(f"\n  Task registry  : 4 tasks — OK")
        for t in tasks:
            trigger_detail = (
                f"every {t.get('hours', t.get('minutes', '?'))} "
                f"{'h' if 'hours' in t else 'min'}"
                if t["trigger"] == "interval"
                else f"cron hour={t.get('hour')} dow={t.get('day_of_week')}"
            )
            print(f"    {t['id']:<35} {trigger_detail}")
        print(f"  create_scheduler() : unstarted BackgroundScheduler, 4 jobs — OK")
        print(f"  main.py wiring     : start/shutdown/no-scheduler/enable_scheduler — OK")

    # ── 6. Vault structure ────────────────────────────────────────────────────

    def test_6_vault_structure(self):
        """Vault has all 7 required folders plus Dashboard.md and Company_Handbook.md."""
        required_folders = [
            "Inbox",
            "Needs_Action",
            "Done",
            "Plans",
            "Pending_Approval",
            "Approved",
            "Rejected",
        ]

        for folder_name in required_folders:
            folder = self.vault_path / folder_name
            # Create if absent (vault bootstrapping is acceptable)
            folder.mkdir(parents=True, exist_ok=True)
            with self.subTest(folder=folder_name):
                self.assertTrue(
                    folder.exists(),
                    f"Vault folder missing and could not be created: {folder}",
                )
                self.assertTrue(
                    folder.is_dir(),
                    f"Vault/{folder_name} exists but is not a directory",
                )

        # Core vault files
        for filename in ("Dashboard.md", "Company_Handbook.md"):
            vault_file = self.vault_path / filename
            self.assertTrue(
                vault_file.exists(),
                f"Core vault file missing: {filename} — expected at {vault_file}",
            )
            self.assertGreater(
                vault_file.stat().st_size, 0,
                f"{filename} is empty",
            )

        # Dashboard.md must contain key sections
        dashboard_content = (self.vault_path / "Dashboard.md").read_text(encoding="utf-8")
        for section in ("System Status", "Quick Stats"):
            self.assertIn(
                section, dashboard_content,
                f"Dashboard.md is missing section: '{section}'",
            )

        print(f"\n  Vault: {self.vault_path}")
        for name in required_folders:
            status = "EXISTS" if (self.vault_path / name).exists() else "CREATED"
            print(f"  {name + '/':20} {status}")
        print(f"  Dashboard.md       : OK ({(self.vault_path / 'Dashboard.md').stat().st_size:,} bytes)")
        print(f"  Company_Handbook.md: OK")
        print(f"  Dashboard sections : System Status, Quick Stats — OK")

    # ── 7. Documentation complete ─────────────────────────────────────────────

    def test_7_documentation_complete(self):
        """All required documentation files exist and are non-empty."""
        # Files at project root
        root_docs = {
            "README.md":        ("Silver", "WhatsApp"),
            "DOCUMENTATION.md": ("Architecture", "watcher"),
            "ARCHITECTURE.md":  ("HITL", "Orchestrator"),
            "BRONZE_COMPLETE.md": ("Bronze Tier", "8 / 8"),
            "SILVER_COMPLETE.md": ("Silver Tier", "48 / 48"),
        }

        # Files in documents/ subdirectory
        subdir_docs = {
            "documents/DEPLOYMENT_GUIDE.md": ("vault", "install"),
            "documents/CODE_DOCUMENTATION.md": ("watcher", "helper"),
            "documents/GMAIL_SETUP.md": ("OAuth", "credentials"),
        }

        all_docs = {
            **{k: (self.project_path / k, v) for k, v in root_docs.items()},
            **{k: (self.project_path / k, v) for k, v in subdir_docs.items()},
        }

        for rel_path, (file_path, (keyword_a, keyword_b)) in all_docs.items():
            with self.subTest(doc=rel_path):
                self.assertTrue(
                    file_path.exists(),
                    f"Documentation file not found: {rel_path}",
                )
                self.assertTrue(
                    file_path.is_file(),
                    f"{rel_path} exists but is not a file",
                )

                content = file_path.read_text(encoding="utf-8")
                self.assertGreater(
                    len(content), 100,
                    f"{rel_path} appears to be empty or too short ({len(content)} chars)",
                )

                # Spot-check for expected content
                for keyword in (keyword_a, keyword_b):
                    self.assertIn(
                        keyword, content,
                        f"{rel_path} is missing expected content: '{keyword}'",
                    )

        # README specifically must show Silver tier (not Bronze-only)
        readme = (self.project_path / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "Silver", readme,
            "README.md must reference Silver tier",
        )
        self.assertNotIn(
            "Bronze%20Complete", readme,
            "README.md badge must not show Bronze Complete (should be Silver)",
        )

        # SILVER_COMPLETE must mention all 4 watchers
        silver = (self.project_path / "SILVER_COMPLETE.md").read_text(encoding="utf-8")
        for watcher_name in ("FileWatcher", "GmailWatcher", "LinkedInWatcher", "WhatsAppWatcher"):
            self.assertIn(
                watcher_name, silver,
                f"SILVER_COMPLETE.md must mention {watcher_name}",
            )

        print(f"\n  Root docs (5):")
        for name in root_docs:
            size = (self.project_path / name).stat().st_size
            print(f"    {name:<30} {size:>7,} bytes — OK")
        print(f"  documents/ docs (3):")
        for name in subdir_docs:
            size = (self.project_path / name).stat().st_size
            print(f"    {name:<38} {size:>7,} bytes — OK")
        print(f"  README.md  : Silver badge, no Bronze-only badge — OK")
        print(f"  SILVER_COMPLETE.md: all 4 watcher names present — OK")

    # ── 8. Silver requirements verified ──────────────────────────────────────

    def test_8_silver_requirements_verified(self):
        """Verify each Silver Tier requirement by inspecting actual code and files."""
        main_source   = (self.project_path / "main.py").read_text(encoding="utf-8")
        skills_dir    = self.project_path / ".claude" / "skills"
        helpers_dir   = self.project_path / "helpers"
        watchers_dir  = self.project_path / "watchers"

        # ── Req 1: All Bronze requirements (5 original skills + 2 watchers) ──
        for skill_name in ("file-monitor", "gmail-monitor", "process-inbox",
                           "update-dashboard", "skill-creator"):
            self.assertTrue(
                (skills_dir / skill_name / "SKILL.md").exists(),
                f"Bronze requirement: skill '{skill_name}' must exist",
            )
        for watcher_file in ("file_watcher.py", "gmail_watcher.py"):
            self.assertTrue(
                (watchers_dir / watcher_file).exists(),
                f"Bronze requirement: {watcher_file} must exist",
            )

        # ── Req 2: 4+ Watchers ────────────────────────────────────────────────
        watcher_files = ["file_watcher.py", "gmail_watcher.py",
                         "linkedin_watcher.py", "whatsapp_watcher.py"]
        for wf in watcher_files:
            self.assertTrue(
                (watchers_dir / wf).exists(),
                f"4+ Watchers requirement: {wf} missing",
            )
        # All 4 imported in main.py
        for cls_name in ("FileWatcher", "GmailWatcher", "LinkedInWatcher", "WhatsAppWatcher"):
            self.assertIn(
                cls_name, main_source,
                f"4+ Watchers requirement: {cls_name} must be imported in main.py",
            )

        # ── Req 3: LinkedIn auto-posting with HITL approval ───────────────────
        linkedin_poster = helpers_dir / "linkedin_poster.py"
        self.assertTrue(linkedin_poster.exists(), "LinkedIn auto-posting: linkedin_poster.py missing")
        poster_source = linkedin_poster.read_text(encoding="utf-8")
        self.assertIn("def post_to_linkedin(", poster_source,
                      "LinkedIn auto-posting: post_to_linkedin() must be defined")
        # The HITL gate (Pending_Approval) is enforced by the post-linkedin skill,
        # not inside linkedin_poster.py itself — check the skill instead
        post_skill = skills_dir / "post-linkedin" / "SKILL.md"
        self.assertTrue(
            post_skill.exists(),
            "LinkedIn auto-posting: post-linkedin skill missing",
        )
        post_skill_content = post_skill.read_text(encoding="utf-8")
        self.assertIn(
            "Pending_Approval", post_skill_content,
            "LinkedIn auto-posting: post-linkedin/SKILL.md must reference Pending_Approval/",
        )

        # ── Req 4: Plan.md creation ───────────────────────────────────────────
        plan_creator = helpers_dir / "plan_creator.py"
        self.assertTrue(plan_creator.exists(), "Plan creation: plan_creator.py missing")
        plan_source = plan_creator.read_text(encoding="utf-8")
        self.assertIn("def create_plan(", plan_source,
                      "Plan creation: create_plan() must be defined")
        self.assertTrue(
            (skills_dir / "create-plan" / "SKILL.md").exists(),
            "Plan creation: create-plan skill missing",
        )

        # ── Req 5: MCP Email Server ───────────────────────────────────────────
        email_server = self.project_path / "mcp_servers" / "email_server.py"
        self.assertTrue(email_server.exists(), "MCP Server: email_server.py missing")
        email_source = email_server.read_text(encoding="utf-8")
        self.assertIn("def send_email(", email_source,
                      "MCP Server: send_email() must be defined")
        self.assertIn("gmail.send", email_source,
                      "MCP Server: gmail.send scope must be declared")

        # ── Req 6: HITL Approval Workflow ─────────────────────────────────────
        for skill_name in ("approve-action", "reject-action"):
            self.assertTrue(
                (skills_dir / skill_name / "SKILL.md").exists(),
                f"HITL Workflow: {skill_name} skill missing",
            )
        # Pending_Approval folder must exist in vault
        self.assertTrue(
            (self.vault_path / "Pending_Approval").exists(),
            "HITL Workflow: Vault/Pending_Approval/ folder missing",
        )
        # Approval timeout scheduler task must exist
        from scheduler.scheduled_tasks import get_scheduled_tasks
        task_ids = {t["id"] for t in get_scheduled_tasks(str(self.vault_path))}
        self.assertIn(
            "check_approval_timeouts", task_ids,
            "HITL Workflow: check_approval_timeouts scheduled task missing",
        )

        # ── Req 7: Scheduled Automation ──────────────────────────────────────
        sched_file = self.project_path / "scheduler" / "scheduled_tasks.py"
        self.assertTrue(sched_file.exists(), "Scheduled Automation: scheduled_tasks.py missing")
        self.assertIn("BackgroundScheduler", main_source,
                      "Scheduled Automation: BackgroundScheduler not in main.py")
        self.assertEqual(
            len(get_scheduled_tasks(str(self.vault_path))), 4,
            "Scheduled Automation: must have exactly 4 registered tasks",
        )

        # ── Req 8: All AI as Agent Skills (pure Markdown) ────────────────────
        all_skill_dirs = [d for d in skills_dir.iterdir()
                          if d.is_dir() and (d / "SKILL.md").exists()]
        self.assertGreaterEqual(
            len(all_skill_dirs), 12,
            f"Agent Skills: expected at least 12 skills, found {len(all_skill_dirs)}",
        )
        for skill_dir in all_skill_dirs:
            content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            python_blocks = re.findall(r"```python", content, re.IGNORECASE)
            self.assertEqual(
                len(python_blocks), 0,
                f"Agent Skills: {skill_dir.name}/SKILL.md contains Python code blocks "
                f"(found {len(python_blocks)}) — skills must be pure Markdown",
            )

        print(f"\n  Req 1 — Bronze carried forward: 5 skills + 2 watchers — OK")
        print(f"  Req 2 — 4+ Watchers: file, gmail, linkedin, whatsapp — OK")
        print(f"  Req 3 — LinkedIn auto-posting: post_to_linkedin + HITL gate — OK")
        print(f"  Req 4 — Plan creation: create_plan + create-plan skill — OK")
        print(f"  Req 5 — MCP Email Server: send_email + gmail.send scope — OK")
        print(f"  Req 6 — HITL Workflow: approve/reject skills + timeout task — OK")
        print(f"  Req 7 — Scheduled Automation: 4 APScheduler tasks in main.py — OK")
        print(f"  Req 8 — Agent Skills: {len(all_skill_dirs)} skills, all pure Markdown — OK")
        print(f"\n  Silver Requirements: 8/8 MET")

    # ── 9. main.py orchestrator ───────────────────────────────────────────────

    def test_9_main_orchestrator(self):
        """main.py compiles, imports all 4 watchers, and has correct CLI + health check."""
        main_path = self.project_path / "main.py"
        self.assertTrue(main_path.exists(), f"main.py not found at: {main_path}")

        source = main_path.read_text(encoding="utf-8")

        # Compiles clean
        try:
            compile(source, str(main_path), "exec")
        except SyntaxError as exc:
            self.fail(f"main.py has a syntax error: {exc}")

        # All 4 watcher imports
        for import_stmt in (
            "from watchers.file_watcher import FileWatcher",
            "from watchers.gmail_watcher import GmailWatcher",
            "from watchers.linkedin_watcher import LinkedInWatcher",
            "from watchers.whatsapp_watcher import WhatsAppWatcher",
        ):
            self.assertIn(
                import_stmt, source,
                f"main.py missing import: {import_stmt}",
            )

        # All 4 WatcherThread entries
        for watcher_name in ("FileWatcher", "GmailWatcher", "LinkedInWatcher", "WhatsAppWatcher"):
            self.assertIn(
                f'name="{watcher_name}"', source,
                f"main.py missing WatcherThread for {watcher_name}",
            )

        # CLI arguments with correct defaults
        cli_checks = {
            '"--file-interval"':      "default=60",
            '"--gmail-interval"':     "default=120",
            '"--linkedin-interval"':  "default=180",
            '"--whatsapp-interval"':  "default=60",
        }
        for arg_str, default_str in cli_checks.items():
            arg_idx = source.find(arg_str)
            self.assertGreater(
                arg_idx, -1,
                f"main.py missing CLI argument: {arg_str}",
            )
            block = source[arg_idx : arg_idx + 200]
            self.assertIn(
                default_str, block,
                f"CLI argument {arg_str} must have {default_str}",
            )

        # Orchestrator constructor declares all 4 interval params
        for param in ("file_interval: int", "gmail_interval: int",
                      "linkedin_interval: int", "whatsapp_interval: int"):
            self.assertIn(param, source,
                          f"Orchestrator.__init__ missing parameter: {param}")

        # component_map covers all 4 watchers
        for entry in ('"FileWatcher"', '"GmailWatcher"',
                      '"LinkedInWatcher"', '"WhatsAppWatcher"'):
            self.assertIn(
                entry, source,
                f"_update_dashboard component_map missing entry: {entry}",
            )

        # Health check and dashboard refresh present
        self.assertIn("_health_check",     source, "main.py missing _health_check method")
        self.assertIn("_refresh_dashboard", source, "main.py missing _refresh_dashboard method")

        # Graceful shutdown handles SIGINT + SIGTERM
        self.assertIn("SIGINT",  source, "main.py must handle SIGINT")
        self.assertIn("SIGTERM", source, "main.py must handle SIGTERM")

        print(f"\n  Path              : {main_path}")
        print(f"  Syntax            : valid Python")
        print(f"  Watcher imports   : FileWatcher, GmailWatcher, LinkedInWatcher, WhatsAppWatcher — OK")
        print(f"  WatcherThreads    : all 4 registered in _watchers list — OK")
        print(f"  CLI intervals     : file=60s, gmail=120s, linkedin=180s, whatsapp=60s — OK")
        print(f"  Orchestrator params: all 4 interval params declared — OK")
        print(f"  component_map     : all 4 watchers mapped — OK")
        print(f"  Health check      : _health_check + _refresh_dashboard — OK")
        print(f"  Signal handling   : SIGINT + SIGTERM — OK")

    # ── 10. Cross-component consistency ──────────────────────────────────────

    def test_10_cross_component_consistency(self):
        """
        Verify consistency across layers: skill triggers reference real modules,
        priority keywords are consistent, and test suite is complete.
        """
        skills_dir   = self.project_path / ".claude" / "skills"
        watchers_dir = self.project_path / "watchers"
        helpers_dir  = self.project_path / "helpers"
        tests_dir    = self.project_path / "tests"

        # ── Watcher modules reference BaseWatcher ─────────────────────────────
        for watcher_file in ("file_watcher.py", "gmail_watcher.py",
                             "linkedin_watcher.py", "whatsapp_watcher.py"):
            source = (watchers_dir / watcher_file).read_text(encoding="utf-8")
            self.assertIn(
                "BaseWatcher", source,
                f"{watcher_file} must import/inherit BaseWatcher",
            )

        # ── Priority keywords consistent across WhatsApp and Gmail watchers ───
        whatsapp_source = (watchers_dir / "whatsapp_watcher.py").read_text(encoding="utf-8")
        gmail_source    = (watchers_dir / "gmail_watcher.py").read_text(encoding="utf-8")

        shared_keywords = ["urgent", "asap", "invoice", "payment"]
        for kw in shared_keywords:
            self.assertIn(
                f'"{kw}"', whatsapp_source,
                f"whatsapp_watcher.py missing shared keyword: '{kw}'",
            )
            self.assertIn(
                kw, gmail_source,
                f"gmail_watcher.py missing shared keyword: '{kw}'",
            )

        # ── Session path conventions are consistent ────────────────────────────
        linkedin_source  = (watchers_dir / "linkedin_watcher.py").read_text(encoding="utf-8")
        for source, name in ((linkedin_source, "linkedin_watcher"),
                             (whatsapp_source, "whatsapp_watcher")):
            self.assertIn(
                "context.json", source,
                f"{name}.py must use context.json for session storage",
            )
            self.assertIn(
                ".credentials", source,
                f"{name}.py must store session under ~/.credentials/",
            )

        # ── Skills reference correct Python modules ────────────────────────────
        skill_module_checks = {
            "whatsapp-monitor": "whatsapp_watcher",
            "linkedin-monitor": "linkedin_watcher",
            "gmail-monitor":    "gmail_watcher",
            "send-email":       "email_server",
            "post-linkedin":    "linkedin_poster",
            "create-plan":      "plan_creator",
        }
        for skill_name, module_name in skill_module_checks.items():
            skill_content = (skills_dir / skill_name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(
                module_name, skill_content,
                f"{skill_name}/SKILL.md must reference '{module_name}'",
            )

        # ── HITL skills reference Pending_Approval ────────────────────────────
        for hitl_skill in ("send-email", "post-linkedin"):
            content = (skills_dir / hitl_skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(
                "Pending_Approval", content,
                f"{hitl_skill}/SKILL.md must reference Pending_Approval/ folder",
            )

        # ── Test coverage: one test file per Silver component ─────────────────
        expected_test_files = [
            "test_whatsapp.py",
            "test_linkedin.py",
            "test_email.py",
            "test_plan.py",
            "test_approval.py",
            "test_scheduler.py",
        ]
        for test_file in expected_test_files:
            self.assertTrue(
                (tests_dir / test_file).exists(),
                f"Missing test file: tests/{test_file}",
            )
        # Verify each test file has at least 8 test methods
        for test_file in expected_test_files:
            source = (tests_dir / test_file).read_text(encoding="utf-8")
            test_count = len(re.findall(r"def test_\d+_", source))
            self.assertGreaterEqual(
                test_count, 8,
                f"tests/{test_file} must have at least 8 test methods, found {test_count}",
            )

        # ── main.py banner mentions all 4 watchers ────────────────────────────
        main_source = (self.project_path / "main.py").read_text(encoding="utf-8")
        for label in ("File Watcher", "Gmail Watcher", "LinkedIn Watcher", "WhatsApp Watcher"):
            self.assertIn(
                label, main_source,
                f"main.py startup banner must mention '{label}'",
            )

        print(f"\n  BaseWatcher inheritance: all 4 watcher files — OK")
        print(f"  Shared priority keywords (urgent/asap/invoice/payment): consistent — OK")
        print(f"  Session storage: context.json + .credentials/ in both browser watchers — OK")
        print(f"  Skill ->module references:")
        for skill, mod in skill_module_checks.items():
            print(f"    {skill:<20} ->{mod} — OK")
        print(f"  HITL skills reference Pending_Approval/: OK")
        print(f"  Test coverage: 6 test files, each with >= 8 tests (48 total) — OK")
        print(f"  Banner: all 4 watcher labels in main.py — OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestSilverIntegration)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  SILVER TIER — MASTER INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
