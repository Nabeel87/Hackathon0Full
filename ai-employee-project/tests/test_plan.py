"""
tests/test_plan.py

Plan Creator Helper & create-plan skill — comprehensive integration tests.

Tests cover file/function existence, skill structure, Plans/ folder layout,
complexity analysis, plan generation, plan file format, and load_task_from_file
round-trip parsing.  No external APIs or credentials required.

Run:
    python -m pytest tests/test_plan.py -v
    python tests/test_plan.py              # standalone (no pytest needed)

NOTE ON FUNCTION NAMES
----------------------
The spec mentions analyze_task_complexity() and update_plan_progress() but the
actual helpers/plan_creator.py exposes:
  Public:   create_plan(), load_task_from_file(), list_plans()
  Internal: _analyse_task()   (complexity / domain detection)
Tests are written against what actually exists.
"""

import inspect
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VAULT = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")


# ── Test suite ────────────────────────────────────────────────────────────────

class TestPlanCreation(unittest.TestCase):
    """Full integration test suite for the Plan Creator (Silver Tier)."""

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

    # ── 1. Helper file exists ─────────────────────────────────────────────────

    def test_1_plan_creator_exists(self):
        """helpers/plan_creator.py exists and is a valid Python file."""
        helper_path = self.project_path / "helpers" / "plan_creator.py"

        self.assertTrue(
            helper_path.exists(),
            f"helpers/plan_creator.py not found at: {helper_path}",
        )
        self.assertTrue(helper_path.is_file(), "plan_creator.py path is not a file")
        self.assertEqual(helper_path.suffix, ".py", "plan_creator must be a .py file")

        source = helper_path.read_text(encoding="utf-8")
        self.assertGreater(len(source), 200, "plan_creator.py is suspiciously short")

        # Must compile without SyntaxError
        try:
            compile(source, str(helper_path), "exec")
        except SyntaxError as exc:
            self.fail(f"plan_creator.py has a syntax error: {exc}")

        # Key identifiers must be present
        for identifier in ("create_plan", "load_task_from_file", "list_plans", "_analyse_task"):
            self.assertIn(identifier, source, f"Expected identifier '{identifier}' not found")

        print(f"\n  Path     : {helper_path}")
        print(f"  Size     : {len(source):,} chars")
        print(f"  Syntax   : valid Python")
        print(f"  Functions: create_plan, load_task_from_file, list_plans, _analyse_task — OK")

    # ── 2. Helper functions ───────────────────────────────────────────────────

    def test_2_plan_creator_functions(self):
        """Public functions exist, are callable, and have the correct signatures."""
        from helpers.plan_creator import create_plan, load_task_from_file, list_plans, _analyse_task

        for fn in (create_plan, load_task_from_file, list_plans, _analyse_task):
            self.assertTrue(callable(fn), f"{fn.__name__} is not callable")

        # ── create_plan ───────────────────────────────────────────────────────
        sig    = inspect.signature(create_plan)
        params = list(sig.parameters.keys())

        for required in ("task_description", "vault_path"):
            self.assertIn(required, params, f"create_plan missing required param: '{required}'")

        self.assertIn("source_file", params, "create_plan should accept 'source_file' override")
        self.assertIsNot(
            sig.parameters["source_file"].default,
            inspect.Parameter.empty,
            "source_file must be optional (have a default value)",
        )

        # ── load_task_from_file ───────────────────────────────────────────────
        dsig    = inspect.signature(load_task_from_file)
        dparams = list(dsig.parameters.keys())
        self.assertIn("file_path", dparams, "load_task_from_file missing 'file_path' param")

        # ── list_plans ────────────────────────────────────────────────────────
        lsig    = inspect.signature(list_plans)
        lparams = list(lsig.parameters.keys())
        self.assertIn("vault_path", lparams, "list_plans missing 'vault_path' param")

        # ── _analyse_task ─────────────────────────────────────────────────────
        asig    = inspect.signature(_analyse_task)
        aparams = list(asig.parameters.keys())
        self.assertIn("description", aparams, "_analyse_task missing 'description' param")

        print(f"\n  create_plan params       : {params}")
        print(f"  load_task_from_file params: {dparams}")
        print(f"  list_plans params         : {lparams}")
        print(f"  _analyse_task params      : {aparams}")
        print(f"  All functions callable: OK")

    # ── 3. Skill file ─────────────────────────────────────────────────────────

    def test_3_create_plan_skill_exists(self):
        """create-plan SKILL.md exists, has valid frontmatter, and is pure Markdown."""
        skill_path = self.project_path / ".claude" / "skills" / "create-plan" / "SKILL.md"

        self.assertTrue(
            skill_path.exists(),
            f"create-plan SKILL.md not found at: {skill_path}",
        )

        content = skill_path.read_text(encoding="utf-8")

        # Frontmatter
        self.assertTrue(content.startswith("---"), "SKILL.md must start with '---' frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter not properly closed with '---'")

        frontmatter = parts[1]

        for field in ("name:", "description:", "triggers:", "tier:"):
            self.assertIn(field, frontmatter, f"Frontmatter missing field: '{field}'")

        self.assertIn("create-plan", frontmatter, "Frontmatter 'name' must be 'create-plan'")

        # At least two triggers
        trigger_items = re.findall(r"^\s+-\s+\S", frontmatter, re.MULTILINE)
        self.assertGreaterEqual(len(trigger_items), 2, "triggers list must have at least 2 items")

        # Required body sections
        for section in ("## Purpose", "## Process", "## How to Run",
                         "## Expected Output", "## Dependencies", "## Notes"):
            self.assertIn(section, content, f"SKILL.md missing required section: '{section}'")

        # References the correct helper module
        self.assertIn("plan_creator", content, "SKILL.md must reference 'plan_creator' helper")

        # Pure Markdown — no Python code blocks
        python_blocks = re.findall(r"```python", content, re.IGNORECASE)
        self.assertEqual(
            len(python_blocks), 0,
            f"SKILL.md must not contain ```python blocks (found {len(python_blocks)})",
        )

        # Complexity guidance present
        self.assertIn(
            "complex", content.lower(),
            "SKILL.md must explain when tasks are complex enough to need a plan",
        )

        print(f"\n  Path      : {skill_path}")
        print(f"  Size      : {len(content):,} chars")
        print(f"  Frontmatter: name=create-plan, triggers ({len(trigger_items)}), tier — OK")
        print(f"  All required sections present: OK")
        print(f"  plan_creator reference: OK")
        print(f"  No Python code blocks : OK")

    # ── 4. Plans folder ───────────────────────────────────────────────────────

    def test_4_plans_folder_exists(self):
        """Plans/ folder exists (or is created) in vault and is writable."""
        plans_dir = self.vault_path / "Plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        self.assertTrue(plans_dir.exists(), f"Plans/ could not be created at: {plans_dir}")
        self.assertTrue(plans_dir.is_dir(), "Plans/ path exists but is not a directory")

        # Write-test: create and immediately remove a probe file
        probe = plans_dir / ".write_test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            writable = True
        except OSError:
            writable = False

        self.assertTrue(writable, f"Plans/ directory is not writable: {plans_dir}")

        # Count existing plans (informational)
        existing = list(plans_dir.glob("PLAN_*.md"))
        print(f"\n  Plans dir  : {plans_dir}")
        print(f"  Writable   : OK")
        print(f"  Existing plans: {len(existing)}")

    # ── 5. Complexity analysis ────────────────────────────────────────────────

    def test_5_complexity_analysis(self):
        """_analyse_task() correctly classifies task complexity and domain."""
        from helpers.plan_creator import _analyse_task

        # ── Low complexity ─────────────────────────────────────────────────────
        low_result = _analyse_task("Fix typo in README")
        self.assertIn(
            "complexity", low_result,
            "_analyse_task must return a dict with 'complexity' key",
        )
        self.assertIn(
            "domain", low_result,
            "_analyse_task must return a dict with 'domain' key",
        )
        self.assertEqual(
            low_result["complexity"], "low",
            f"'Fix typo in README' should be 'low' complexity, got: {low_result['complexity']}",
        )

        # ── High complexity ────────────────────────────────────────────────────
        high_result = _analyse_task(
            "Migrate the entire application database from SQLite to PostgreSQL, "
            "including schema redesign, data migration scripts, index optimisation, "
            "rollback procedures, and zero-downtime deployment strategy"
        )
        self.assertEqual(
            high_result["complexity"], "high",
            f"Migration task should be 'high' complexity, got: {high_result['complexity']}",
        )
        self.assertEqual(
            high_result["domain"], "database",
            f"Migration task should be 'database' domain, got: {high_result['domain']}",
        )

        # ── Medium complexity ──────────────────────────────────────────────────
        medium_result = _analyse_task("Implement user authentication module for the API")
        self.assertEqual(
            medium_result["complexity"], "medium",
            f"Auth module task should be 'medium' complexity, got: {medium_result['complexity']}",
        )
        # Should detect api or security domain
        self.assertIn(
            medium_result["domain"], ("api", "security", "backend", "general"),
            f"Unexpected domain for auth task: {medium_result['domain']}",
        )

        # ── Domain detection ───────────────────────────────────────────────────
        email_result = _analyse_task("Send invoice email to client via Gmail")
        self.assertEqual(
            email_result["domain"], "email",
            f"Email task should be 'email' domain, got: {email_result['domain']}",
        )

        linkedin_result = _analyse_task("Post LinkedIn update about new product launch")
        self.assertEqual(
            linkedin_result["domain"], "linkedin",
            f"LinkedIn task should be 'linkedin' domain, got: {linkedin_result['domain']}",
        )

        # ── Return structure ───────────────────────────────────────────────────
        for key in ("complexity", "domain", "word_count", "keywords"):
            self.assertIn(key, low_result, f"_analyse_task result missing key: '{key}'")

        self.assertIsInstance(low_result["word_count"], int, "word_count must be an int")
        self.assertIsInstance(low_result["keywords"],   set,  "keywords must be a set")

        print(f"\n  'Fix typo in README'          → complexity=low — OK")
        print(f"  'Migrate database to PostgreSQL' → complexity=high, domain=database — OK")
        print(f"  'Implement auth module'          → complexity=medium — OK")
        print(f"  'Send invoice email'             → domain=email — OK")
        print(f"  'Post LinkedIn update'           → domain=linkedin — OK")
        print(f"  Return structure (complexity, domain, word_count, keywords): OK")

    # ── 6. Plan creation ──────────────────────────────────────────────────────

    def test_6_plan_creation(self):
        """create_plan() generates a PLAN_*.md file in Plans/ and returns its Path."""
        from helpers.plan_creator import create_plan

        task = "Design and implement a REST API endpoint for user profile updates"

        plan_path = create_plan(
            task_description=task,
            vault_path=self.vault_path,
        )
        self._temp_files.append(plan_path)

        self.assertIsInstance(plan_path, Path, "create_plan must return a Path object")
        self.assertTrue(plan_path.exists(), f"Plan file not found at: {plan_path}")
        self.assertEqual(plan_path.suffix, ".md", "Plan file must be a .md file")

        # Filename format: PLAN_YYYYMMDD_HHMMSS_<slug>.md
        self.assertRegex(
            plan_path.name,
            r"^PLAN_\d{8}_\d{6}_\w+\.md$",
            f"Plan filename must match PLAN_YYYYMMDD_HHMMSS_slug.md, got: {plan_path.name}",
        )

        # File must be in Plans/
        self.assertEqual(
            plan_path.parent.name, "Plans",
            f"Plan must be saved in Plans/, got: {plan_path.parent}",
        )

        # File must have content
        content = plan_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 200, "Plan file is suspiciously short")

        # Task description must appear verbatim
        self.assertIn(task, content, "Task description must appear verbatim in the plan")

        print(f"\n  Plan file: {plan_path.name}")
        print(f"  Size     : {len(content):,} chars")
        print(f"  Location : Plans/ — OK")
        print(f"  Filename format: PLAN_YYYYMMDD_HHMMSS_slug.md — OK")
        print(f"  Task description present: OK")

    # ── 7. Plan file format ───────────────────────────────────────────────────

    def test_7_plan_format(self):
        """Generated plan has correct YAML frontmatter and all required body sections."""
        from helpers.plan_creator import create_plan

        task = "Migrate SQLite database to PostgreSQL with zero-downtime deployment"

        plan_path = create_plan(
            task_description=task,
            vault_path=self.vault_path,
        )
        self._temp_files.append(plan_path)

        content = plan_path.read_text(encoding="utf-8")

        # ── YAML frontmatter ───────────────────────────────────────────────────
        self.assertTrue(content.startswith("---"), "Plan must start with '---' YAML frontmatter")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter block not properly closed")

        fm = parts[1]

        # Required frontmatter fields
        for field in ("type:", "status:", "created:", "complexity:", "domain:",
                       "total_estimate:", "steps_count:"):
            self.assertIn(field, fm, f"Frontmatter missing required field: '{field}'")

        # Field values
        self.assertIn("type: plan",     fm, "type must be 'plan'")
        self.assertIn("status: active", fm, "status must be 'active' on creation")

        # complexity must be one of the three valid values
        complexity_match = re.search(r"complexity:\s*(\S+)", fm)
        self.assertIsNotNone(complexity_match, "complexity field missing or unparseable")
        self.assertIn(
            complexity_match.group(1), ("low", "medium", "high"),
            f"complexity must be low/medium/high, got: {complexity_match.group(1)}",
        )

        # steps_count must be a positive integer
        steps_match = re.search(r"steps_count:\s*(\d+)", fm)
        self.assertIsNotNone(steps_match, "steps_count field missing or unparseable")
        self.assertGreater(int(steps_match.group(1)), 0, "steps_count must be > 0")

        # created timestamp is ISO format
        created_match = re.search(r"created:\s*(\S+)", fm)
        self.assertIsNotNone(created_match, "created field missing")
        try:
            datetime.fromisoformat(created_match.group(1))
        except ValueError:
            self.fail(f"created timestamp is not valid ISO format: {created_match.group(1)}")

        # ── Required body sections ─────────────────────────────────────────────
        for section in (
            "## Task Description",
            "## Resources Needed",
            "## Steps",
            "## Success Criteria",
            "## Notes",
        ):
            self.assertIn(section, content, f"Plan body missing required section: '{section}'")

        # ── Steps must have numbered entries with checkboxes ───────────────────
        step_headers = re.findall(r"^### Step \d+:", content, re.MULTILINE)
        self.assertGreater(len(step_headers), 0, "Plan must contain at least one ### Step N: entry")

        checkboxes = re.findall(r"- \[ \] Complete", content)
        self.assertEqual(
            len(checkboxes), len(step_headers),
            "Every step must have a '- [ ] Complete' checkbox",
        )

        # ── Success criteria must have checkboxes ──────────────────────────────
        sc_start = content.find("## Success Criteria")
        sc_end   = content.find("##", sc_start + 1) if content.find("##", sc_start + 1) != -1 else len(content)
        sc_block = content[sc_start:sc_end]
        sc_items = re.findall(r"- \[ \]", sc_block)
        self.assertGreater(len(sc_items), 0, "Success Criteria must have at least one '- [ ]' item")

        # ── Resources must have checklist items ────────────────────────────────
        self.assertIn("- [ ]", content[content.find("## Resources Needed"):],
                      "Resources section must have checklist items")

        n_steps  = int(steps_match.group(1))
        print(f"\n  Plan file : {plan_path.name}")
        print(f"  Complexity: {complexity_match.group(1)}")
        print(f"  Steps     : {n_steps} ({len(step_headers)} ### Step headers found)")
        print(f"  Checkboxes: {len(checkboxes)} step checkboxes — OK")
        print(f"  Success criteria: {len(sc_items)} items — OK")
        print(f"  All 5 sections (Task Description, Resources, Steps, Success Criteria, Notes): OK")
        print(f"  created ISO timestamp: {created_match.group(1)} — OK")

    # ── 8. load_task_from_file round-trip ─────────────────────────────────────

    def test_8_load_task_from_file(self):
        """load_task_from_file() correctly parses vault cards and generated plan files."""
        from helpers.plan_creator import create_plan, load_task_from_file

        # ── Round-trip: create plan → load it back ─────────────────────────────
        task = "Deploy containerised backend service to AWS ECS with health checks"

        plan_path = create_plan(task_description=task, vault_path=self.vault_path)
        self._temp_files.append(plan_path)

        result = load_task_from_file(plan_path)

        self.assertIsInstance(result, dict, "load_task_from_file must return a dict")
        for key in ("description", "source_type", "raw_content"):
            self.assertIn(key, result, f"Result dict missing key: '{key}'")

        self.assertIsInstance(result["description"],  str, "description must be a str")
        self.assertIsInstance(result["source_type"],  str, "source_type must be a str")
        self.assertIsInstance(result["raw_content"],  str, "raw_content must be a str")

        # raw_content must be the full file text
        self.assertEqual(
            result["raw_content"],
            plan_path.read_text(encoding="utf-8"),
            "raw_content must match the full file text",
        )

        # description must be non-empty
        self.assertGreater(len(result["description"]), 0, "description must not be empty")

        print(f"\n  Source plan: {plan_path.name}")
        print(f"  description (first 80): {result['description'][:80]!r}")
        print(f"  source_type: {result['source_type']!r}")
        print(f"  raw_content length: {len(result['raw_content']):,} chars")

        # ── Parse a mock email vault card ──────────────────────────────────────
        mock_card = self.vault_path / "Inbox" / "_test_email_card.md"
        mock_card.parent.mkdir(parents=True, exist_ok=True)
        self._temp_files.append(mock_card)

        mock_card.write_text(
            "---\n"
            "type: email\n"
            "from: \"client@example.com\"\n"
            "subject: \"Urgent: please review the contract\"\n"
            "priority: high\n"
            "status: pending\n"
            "---\n"
            "\n"
            "# Email: Urgent: please review the contract\n"
            "\n"
            "**From:** client@example.com\n"
            "\n"
            "## Snippet\n\n"
            "> Please review and sign the attached contract by Friday.\n",
            encoding="utf-8",
        )

        email_result = load_task_from_file(mock_card)

        self.assertIn(
            "email", email_result["source_type"],
            f"Email card source_type should contain 'email', got: {email_result['source_type']!r}",
        )
        # description should extract subject or first body paragraph
        self.assertGreater(
            len(email_result["description"]), 0,
            "Email card description must not be empty",
        )

        print(f"\n  Mock email card: {mock_card.name}")
        print(f"  source_type: {email_result['source_type']!r} — OK")
        print(f"  description: {email_result['description'][:80]!r}")

        # ── File not found raises FileNotFoundError ────────────────────────────
        with self.assertRaises(
            FileNotFoundError,
            msg="load_task_from_file must raise FileNotFoundError for missing files",
        ):
            load_task_from_file(self.vault_path / "Needs_Action" / "_nonexistent.md")

        print(f"  Missing file raises FileNotFoundError — OK")


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all():
    suite  = unittest.TestLoader().loadTestsFromTestCase(TestPlanCreation)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  PLAN CREATOR — INTEGRATION TEST SUITE")
    print("=" * 65 + "\n")
    success = _run_all()
    print("\n" + "=" * 65)
    print(f"  {'ALL TESTS PASSED' if success else 'SOME TESTS FAILED'}")
    print("=" * 65 + "\n")
    sys.exit(0 if success else 1)
