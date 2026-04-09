"""
helpers/plan_creator.py — Plan Creator Helper (Silver Tier)
============================================================
Generates structured Plan.md files for complex multi-step tasks.

Accepts a task description (free text or parsed from a Needs_Action/ vault card),
analyses complexity, breaks the work into numbered steps with time estimates and
dependencies, defines success criteria, and saves the result to vault Plans/.

Public API
----------
  create_plan(task_description, vault_path, source_file=None)  → Path
  load_task_from_file(file_path)                               → dict
  list_plans(vault_path)                                       → list[Path]

CLI
---
  python helpers/plan_creator.py --task "Migrate database to PostgreSQL"
  python helpers/plan_creator.py --source Needs_Action/GMAIL_20260409_123000.md
  python helpers/plan_creator.py --list
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

# Keyword sets used for complexity analysis and step-template selection
_COMPLEXITY_HIGH = {
    "migrate", "migration", "refactor", "architecture", "deploy", "deployment",
    "integration", "security", "audit", "compliance", "overhaul", "redesign",
    "system", "infrastructure", "pipeline", "automate", "automation",
}
_COMPLEXITY_MEDIUM = {
    "implement", "build", "create", "develop", "update", "upgrade", "add",
    "feature", "module", "service", "api", "endpoint", "report", "analysis",
    "review", "test", "testing", "document", "documentation",
}
_COMPLEXITY_LOW = {
    "fix", "bug", "patch", "hotfix", "typo", "rename", "move", "delete",
    "remove", "change", "tweak", "minor", "small", "quick",
}

# Domain tags — used to select the most relevant step template
_DOMAIN_TAGS: dict[str, set[str]] = {
    "database":   {"database", "db", "sql", "postgres", "mysql", "sqlite", "mongo", "schema", "migration"},
    "api":        {"api", "endpoint", "rest", "graphql", "webhook", "integration", "http", "request"},
    "frontend":   {"ui", "frontend", "react", "html", "css", "javascript", "typescript", "page", "form"},
    "backend":    {"backend", "server", "service", "worker", "queue", "celery", "django", "flask", "fastapi"},
    "devops":     {"deploy", "docker", "kubernetes", "ci", "cd", "pipeline", "infra", "cloud", "aws", "azure"},
    "email":      {"email", "gmail", "smtp", "notification", "send", "inbox"},
    "linkedin":   {"linkedin", "post", "social", "network", "connection"},
    "data":       {"data", "csv", "report", "analysis", "dashboard", "metric", "stats", "analytics"},
    "security":   {"auth", "authentication", "authorization", "oauth", "token", "permission", "security", "ssl"},
    "testing":    {"test", "testing", "pytest", "unittest", "coverage", "qa", "quality"},
    "document":   {"document", "documentation", "readme", "wiki", "guide", "spec", "plan"},
    "file":       {"file", "folder", "directory", "upload", "download", "storage", "monitor"},
}


# ── Complexity analysis ───────────────────────────────────────────────────────

def _analyse_task(description: str) -> dict:
    """
    Parse the task description and return a metadata dict:
      complexity   — 'low' | 'medium' | 'high'
      domain       — primary domain tag (e.g. 'database', 'api', 'general')
      word_count   — number of words in the description
      keywords     — matched keyword set
    """
    words = set(re.findall(r"[a-z]+", description.lower()))

    high_hits   = words & _COMPLEXITY_HIGH
    medium_hits = words & _COMPLEXITY_MEDIUM
    low_hits    = words & _COMPLEXITY_LOW

    if high_hits or len(description.split()) > 30:
        complexity = "high"
    elif medium_hits or len(description.split()) > 10:
        complexity = "medium"
    else:
        complexity = "low"

    # Primary domain: whichever tag set has the most hits
    domain = "general"
    best   = 0
    for tag, kws in _DOMAIN_TAGS.items():
        hits = len(words & kws)
        if hits > best:
            best   = hits
            domain = tag

    return {
        "complexity": complexity,
        "domain":     domain,
        "word_count": len(description.split()),
        "keywords":   high_hits | medium_hits | low_hits,
    }


# ── Step templates ────────────────────────────────────────────────────────────

def _generate_steps(description: str, meta: dict) -> list[dict]:
    """
    Return a list of step dicts based on complexity and domain.
    Each dict has: number, title, details, estimate, dependencies.
    """
    complexity = meta["complexity"]
    domain     = meta["domain"]

    # Universal phases every plan includes
    steps: list[dict] = [
        {
            "number":       1,
            "title":        "Understand and scope the task",
            "details":      (
                "Re-read the full task description. Clarify any ambiguities with the "
                "stakeholder. Identify what is explicitly in-scope and what is out-of-scope. "
                "Confirm the definition of done."
            ),
            "estimate":     "15–30 min",
            "dependencies": [],
        },
        {
            "number":       2,
            "title":        "Gather requirements and resources",
            "details":      (
                "List all inputs, credentials, access rights, external systems, "
                "and documentation needed. Identify blockers and resolve them before "
                "proceeding to implementation."
            ),
            "estimate":     "15–30 min",
            "dependencies": [1],
        },
    ]

    # Domain-specific middle steps
    domain_steps = _domain_steps(domain, complexity)
    for i, ds in enumerate(domain_steps, start=3):
        ds["number"]       = i
        ds["dependencies"] = [i - 1]
        steps.append(ds)

    # Complexity-driven extra steps for high-complexity tasks
    if complexity == "high":
        n = len(steps) + 1
        steps.append({
            "number":       n,
            "title":        "Risk assessment and rollback plan",
            "details":      (
                "Identify the top 3 risks (probability × impact). Define a rollback "
                "procedure for each risk. Document the rollback steps before proceeding."
            ),
            "estimate":     "30–60 min",
            "dependencies": [n - 1],
        })

    # Universal closing phases
    n = len(steps) + 1
    steps.append({
        "number":       n,
        "title":        "Test and validate",
        "details":      (
            "Run all relevant tests. Verify the outcome matches the success criteria "
            "defined in this plan. Check edge cases. Document any deviations."
        ),
        "estimate":     "30–60 min" if complexity == "high" else "15–30 min",
        "dependencies": [n - 1],
    })

    n += 1
    steps.append({
        "number":       n,
        "title":        "Document and close",
        "details":      (
            "Update any relevant README, runbook, or Dashboard. Archive this plan "
            "to Done/. Notify stakeholders of completion."
        ),
        "estimate":     "15–30 min",
        "dependencies": [n - 1],
    })

    return steps


def _domain_steps(domain: str, complexity: str) -> list[dict]:
    """Return domain-specific implementation steps (without number/dependencies set)."""

    templates: dict[str, list[dict]] = {

        "database": [
            {"title": "Design schema changes",
             "details": "Define the target schema. List all tables, columns, indexes, and constraints being added or modified. Write the migration script.",
             "estimate": "30–60 min"},
            {"title": "Back up existing data",
             "details": "Take a full database backup. Verify the backup can be restored. Store the backup file in a safe location.",
             "estimate": "15–30 min"},
            {"title": "Apply migration in staging",
             "details": "Run the migration script against a staging environment. Verify row counts, constraints, and application behaviour.",
             "estimate": "30–60 min"},
            {"title": "Apply migration in production",
             "details": "Schedule a maintenance window if needed. Run migration script. Monitor logs for errors. Verify application is healthy.",
             "estimate": "30–60 min"},
        ],

        "api": [
            {"title": "Define API contract",
             "details": "Specify endpoints, HTTP methods, request/response schemas, authentication, error codes, and versioning strategy.",
             "estimate": "30–60 min"},
            {"title": "Implement endpoints",
             "details": "Write the route handlers, business logic, and data validation. Follow existing code style and error handling patterns.",
             "estimate": "1–3 h"},
            {"title": "Write integration tests",
             "details": "Test each endpoint with valid, invalid, and edge-case inputs. Verify status codes, response bodies, and error messages.",
             "estimate": "30–60 min"},
        ],

        "frontend": [
            {"title": "Design UI layout and components",
             "details": "Sketch or wireframe the new UI. Identify reusable components. Confirm design with stakeholder.",
             "estimate": "30–60 min"},
            {"title": "Implement components",
             "details": "Build the UI components. Follow existing design system tokens (colours, typography, spacing). Handle loading and error states.",
             "estimate": "1–3 h"},
            {"title": "Connect to data / API",
             "details": "Wire components to the backend or API. Validate data flow end-to-end. Handle async states.",
             "estimate": "30–60 min"},
        ],

        "backend": [
            {"title": "Design service interface",
             "details": "Define the public interface for the service/module (inputs, outputs, errors). Agree on contracts with dependent services.",
             "estimate": "20–40 min"},
            {"title": "Implement business logic",
             "details": "Write the core logic. Keep functions small and testable. Handle all identified error paths.",
             "estimate": "1–3 h"},
            {"title": "Write unit tests",
             "details": "Cover the happy path, edge cases, and error branches. Target ≥80% coverage for new code.",
             "estimate": "30–60 min"},
        ],

        "devops": [
            {"title": "Provision infrastructure",
             "details": "Define required resources (compute, storage, networking). Apply IaC (Terraform/CloudFormation) or manual setup steps. Confirm in staging.",
             "estimate": "30–90 min"},
            {"title": "Configure CI/CD pipeline",
             "details": "Add or update pipeline stages: build, test, deploy. Set environment variables and secrets in the CI system.",
             "estimate": "30–60 min"},
            {"title": "Deploy and smoke-test",
             "details": "Deploy to staging. Run smoke tests. Verify health checks pass. Deploy to production if staging is healthy.",
             "estimate": "30–60 min"},
        ],

        "email": [
            {"title": "Draft email content",
             "details": "Write the subject line and body. Keep it concise. Avoid jargon. Attach required files.",
             "estimate": "15–30 min"},
            {"title": "Route through approval workflow",
             "details": "Create the draft in Pending_Approval/ via the send-email skill. Wait for human approval before sending.",
             "estimate": "Variable"},
            {"title": "Send and confirm delivery",
             "details": "Send via Gmail API. Verify the message appears in Sent. Log the outcome and message ID.",
             "estimate": "5–10 min"},
        ],

        "linkedin": [
            {"title": "Draft LinkedIn post content",
             "details": "Write the post text. Keep it professional. Include a clear hook, value statement, and call to action. Prepare any image.",
             "estimate": "15–30 min"},
            {"title": "Route through approval workflow",
             "details": "Submit via the post-linkedin skill. Wait for human approval before publishing.",
             "estimate": "Variable"},
            {"title": "Publish and engage",
             "details": "Post is published after approval. Monitor early comments. Respond within 24 hours.",
             "estimate": "5–10 min"},
        ],

        "data": [
            {"title": "Define metrics and data sources",
             "details": "List every metric needed, its source system, and refresh frequency. Confirm availability of required data.",
             "estimate": "20–40 min"},
            {"title": "Extract and transform data",
             "details": "Write or configure the ETL/ELT process. Handle nulls, duplicates, and schema changes. Validate row counts.",
             "estimate": "30–90 min"},
            {"title": "Build report or visualisation",
             "details": "Create the dashboard, chart, or report output. Verify numbers against source data. Share with stakeholders.",
             "estimate": "30–60 min"},
        ],

        "security": [
            {"title": "Identify trust boundaries and threat model",
             "details": "Map data flows, authentication points, and sensitive assets. List the top 5 threats (STRIDE or OWASP).",
             "estimate": "30–60 min"},
            {"title": "Implement security controls",
             "details": "Apply the required controls (auth, validation, encryption, rate limiting). Follow least-privilege principle.",
             "estimate": "1–3 h"},
            {"title": "Security review and penetration test",
             "details": "Run static analysis (bandit, semgrep) and manual review. Test for common vulnerabilities. Fix all critical/high findings.",
             "estimate": "30–90 min"},
        ],

        "testing": [
            {"title": "Define test scope and strategy",
             "details": "List what needs to be tested: unit, integration, e2e, performance. Set coverage targets.",
             "estimate": "15–30 min"},
            {"title": "Write and run tests",
             "details": "Implement all test cases. Run the suite. Fix failures. Ensure CI passes.",
             "estimate": "1–2 h"},
            {"title": "Review coverage and document gaps",
             "details": "Check coverage report. Document known gaps with justification. Update test README.",
             "estimate": "15–30 min"},
        ],

        "document": [
            {"title": "Outline document structure",
             "details": "List all sections, headers, and key points to cover. Confirm scope with stakeholder.",
             "estimate": "15–30 min"},
            {"title": "Write first draft",
             "details": "Write the full document. Use clear, plain language. Include examples, diagrams, and code snippets where helpful.",
             "estimate": "1–2 h"},
            {"title": "Review and publish",
             "details": "Proofread for accuracy and clarity. Get a peer review if required. Publish to the agreed location.",
             "estimate": "15–30 min"},
        ],

        "file": [
            {"title": "Define file handling rules",
             "details": "Document what file types to watch, where to move them, and what triggers an action.",
             "estimate": "15–30 min"},
            {"title": "Implement file processing logic",
             "details": "Write or configure the watcher/processor. Handle edge cases (permissions, duplicates, large files).",
             "estimate": "30–60 min"},
        ],

        "general": [
            {"title": "Research and design approach",
             "details": "Research existing solutions or patterns relevant to this task. Choose the simplest viable approach. Document the decision.",
             "estimate": "20–40 min"},
            {"title": "Implement the solution",
             "details": "Execute the implementation in small, testable increments. Commit frequently. Keep changes reversible.",
             "estimate": "1–3 h"},
            {"title": "Review and refine",
             "details": "Review the output against the original requirements. Refine as needed. Confirm all acceptance criteria are met.",
             "estimate": "15–30 min"},
        ],
    }

    return [dict(s) for s in templates.get(domain, templates["general"])]


# ── Success criteria ──────────────────────────────────────────────────────────

def _success_criteria(description: str, meta: dict) -> list[str]:
    """Return a list of measurable success criteria for the plan."""
    domain = meta["domain"]

    base = [
        "All planned steps are completed and checked off",
        "No critical errors or regressions introduced",
        "Outcome is reviewed and accepted by the stakeholder",
        "This plan file is moved to Done/ and Dashboard is updated",
    ]

    domain_criteria: dict[str, list[str]] = {
        "database":  ["Migration applied cleanly in production with zero data loss",
                      "All application queries return correct results post-migration"],
        "api":       ["All endpoints return correct status codes and response bodies",
                      "All integration tests pass in CI"],
        "frontend":  ["UI renders correctly in all target browsers",
                      "No accessibility regressions (WCAG AA)"],
        "backend":   ["Unit test coverage ≥ 80% for new code",
                      "Service responds correctly under expected load"],
        "devops":    ["Deployment succeeds with zero downtime",
                      "All health checks pass post-deployment"],
        "email":     ["Email delivered and appears in recipient's inbox",
                      "Message ID logged in logs/email_sent.log"],
        "linkedin":  ["Post published and visible on LinkedIn",
                      "Post URL logged and Dashboard updated"],
        "data":      ["Report/dashboard matches source data within agreed tolerance",
                      "Data refresh process is automated or documented"],
        "security":  ["All critical/high findings resolved",
                      "Static analysis passes with no new high-severity findings"],
        "testing":   ["Test suite passes in CI with ≥ target coverage",
                      "No known critical bugs left unaddressed"],
        "document":  ["Document is published to the agreed location",
                      "At least one peer has reviewed for accuracy"],
        "file":      ["Watcher processes all expected file types correctly",
                      "No files are lost or double-processed"],
        "general":   ["All functional requirements from the task description are met"],
    }

    return base + domain_criteria.get(domain, domain_criteria["general"])


# ── Resources section ─────────────────────────────────────────────────────────

def _resources_section(meta: dict) -> str:
    """Return a markdown checklist of likely resources needed."""
    domain = meta["domain"]

    common = [
        "Access to the vault (AI_Employee_Vault/)",
        "Project repository access",
        "Relevant documentation or specs",
    ]
    domain_resources: dict[str, list[str]] = {
        "database":  ["Database credentials and connection string",
                      "Database client (psql, DBeaver, etc.)",
                      "Backup storage location"],
        "api":       ["API documentation or OpenAPI spec",
                      "Postman / curl for manual testing",
                      "Authentication tokens for target API"],
        "frontend":  ["Design assets / Figma file",
                      "Node.js and relevant package manager",
                      "Browser developer tools"],
        "backend":   ["Local development environment",
                      "Relevant framework documentation",
                      "Database or service connections"],
        "devops":    ["Cloud provider credentials (AWS / Azure / GCP)",
                      "Terraform / IaC tooling",
                      "CI/CD platform access (GitHub Actions, etc.)"],
        "email":     ["Gmail OAuth2 credentials (.credentials/credentials.json)",
                      "Gmail OAuth2 token with send scope (.credentials/token.json)"],
        "linkedin":  ["LinkedIn session file (.credentials/linkedin_session/context.json)"],
        "data":      ["Source data access / database connection",
                      "Reporting tool (Jupyter, Metabase, etc.)",
                      "Output storage location"],
        "security":  ["Threat model or architecture diagram",
                      "Static analysis tools (bandit, semgrep)",
                      "Penetration testing environment"],
        "testing":   ["Test framework installed (pytest, etc.)",
                      "CI/CD pipeline access",
                      "Coverage reporting tool"],
        "document":  ["Template or style guide",
                      "Publishing platform access (Confluence, GitHub wiki, etc.)"],
        "file":      ["File watcher configuration",
                      "Target folder paths and permissions"],
        "general":   ["Any external APIs or services referenced in the task"],
    }

    items = common + domain_resources.get(domain, domain_resources["general"])
    return "\n".join(f"- [ ] {item}" for item in items)


# ── Total time estimate ───────────────────────────────────────────────────────

def _total_estimate(complexity: str) -> str:
    return {
        "low":    "1–2 hours",
        "medium": "2–4 hours",
        "high":   "4–8 hours (may span multiple sessions)",
    }[complexity]


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_plan(
    task_description: str,
    meta: dict,
    steps: list[dict],
    criteria: list[str],
    resources: str,
    created_iso: str,
    source_file: str | None,
) -> str:
    """Build the full Plan.md content string."""

    complexity  = meta["complexity"].title()
    domain      = meta["domain"].title()
    total_time  = _total_estimate(meta["complexity"])

    # ── Steps markdown ─────────────────────────────────────────────────────────
    steps_md = ""
    for step in steps:
        deps = (
            "None"
            if not step["dependencies"]
            else ", ".join(f"Step {d}" for d in step["dependencies"])
        )
        steps_md += (
            f"### Step {step['number']}: {step['title']}\n\n"
            f"{step['details']}\n\n"
            f"- **Estimate:** {step['estimate']}\n"
            f"- **Depends on:** {deps}\n"
            f"- [ ] Complete\n\n"
        )

    # ── Success criteria markdown ──────────────────────────────────────────────
    criteria_md = "\n".join(f"- [ ] {c}" for c in criteria)

    # ── Source reference ───────────────────────────────────────────────────────
    source_line = (
        f"\n**Source file:** `{source_file}`"
        if source_file
        else ""
    )

    return (
        f"---\n"
        f"type: plan\n"
        f"status: active\n"
        f"created: {created_iso}\n"
        f"complexity: {meta['complexity']}\n"
        f"domain: {meta['domain']}\n"
        f"total_estimate: \"{total_time}\"\n"
        f"steps_count: {len(steps)}\n"
        f"---\n"
        f"\n"
        f"# Plan: {task_description[:80]}\n"
        f"\n"
        f"**Created:** {created_iso}  \n"
        f"**Complexity:** {complexity}  \n"
        f"**Domain:** {domain}  \n"
        f"**Total estimate:** {total_time}  \n"
        f"**Steps:** {len(steps)}{source_line}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Task Description\n"
        f"\n"
        f"{task_description}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Resources Needed\n"
        f"\n"
        f"{resources}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Steps\n"
        f"\n"
        f"{steps_md}"
        f"---\n"
        f"\n"
        f"## Success Criteria\n"
        f"\n"
        f"{criteria_md}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Notes\n"
        f"\n"
        f"_Add implementation notes, blockers, and decisions here as you work through the plan._\n"
    )


# ── Source file loader ────────────────────────────────────────────────────────

def load_task_from_file(file_path: str | Path) -> dict:
    """
    Parse a vault card (.md) and extract the task description.

    Supports:
      - Frontmatter fields: 'subject', 'content_preview', 'file_name', 'type'
      - Body: first non-empty paragraph after frontmatter

    Returns dict with keys:
      description  (str)   — best task description found
      source_type  (str)   — 'email' | 'linkedin' | 'file' | 'unknown'
      raw_content  (str)   — full file text
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    raw = path.read_text(encoding="utf-8")

    # Parse frontmatter manually (avoids requiring python-frontmatter at runtime)
    fm: dict[str, str] = {}
    body_text = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip().strip('"').strip("'")
            body_text = parts[2]

    source_type = fm.get("type", "unknown").split("_")[0]

    # Best description: subject → content_preview → file_name → first body paragraph
    description = (
        fm.get("subject")
        or fm.get("content_preview")
        or fm.get("file_name")
        or next(
            (p.strip() for p in body_text.split("\n\n") if p.strip() and not p.startswith("#")),
            path.stem,
        )
    )

    return {
        "description": description,
        "source_type": source_type,
        "raw_content": raw,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def create_plan(
    task_description: str,
    vault_path: str | Path,
    source_file: str | Path | None = None,
) -> Path:
    """
    Generate a structured Plan.md for the given task and save it to vault Plans/.

    Parameters
    ----------
    task_description : Plain-text description of the task to plan.
    vault_path       : Path to AI_Employee_Vault.
    source_file      : Optional path to the vault card that triggered this plan
                       (e.g. a Needs_Action/ file).  Stored as a reference only.

    Returns
    -------
    Path — absolute path of the created PLAN_<timestamp>_<slug>.md file.
    """
    vault  = Path(vault_path)
    plans_dir = vault / "Plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    now        = datetime.now(tz=timezone.utc)
    created_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
    ts_slug     = now.strftime("%Y%m%d_%H%M%S")
    title_slug  = re.sub(r"[^\w]+", "_", task_description[:40].lower()).strip("_")
    plan_name   = f"PLAN_{ts_slug}_{title_slug}.md"

    # Avoid collision in the same second
    plan_path = plans_dir / plan_name
    counter   = 1
    while plan_path.exists():
        plan_path = plans_dir / f"PLAN_{ts_slug}_{title_slug}_{counter}.md"
        counter  += 1

    meta      = _analyse_task(task_description)
    steps     = _generate_steps(task_description, meta)
    criteria  = _success_criteria(task_description, meta)
    resources = _resources_section(meta)

    source_ref = str(source_file) if source_file else None

    content = _render_plan(
        task_description=task_description,
        meta=meta,
        steps=steps,
        criteria=criteria,
        resources=resources,
        created_iso=created_iso,
        source_file=source_ref,
    )

    plan_path.write_text(content, encoding="utf-8")

    # Update dashboard activity (soft import — non-fatal if dashboard_updater unavailable)
    try:
        from helpers.dashboard_updater import update_activity
        update_activity(vault, f"Plan created: {task_description[:60]}")
    except Exception:
        pass

    return plan_path


def list_plans(vault_path: str | Path) -> list[Path]:
    """Return all PLAN_*.md files in vault Plans/, newest first."""
    plans_dir = Path(vault_path) / "Plans"
    if not plans_dir.exists():
        return []
    return sorted(
        plans_dir.glob("PLAN_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Employee Plan Creator — generate structured Plan.md files"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task",   type=str, help="Task description (free text)")
    group.add_argument("--source", type=str, help="Path to a vault card to derive task from")
    group.add_argument("--list",   action="store_true", help="List existing plans")

    parser.add_argument(
        "--vault",
        type=str,
        default=str(DEFAULT_VAULT),
        help="Path to AI_Employee_Vault",
    )
    args = parser.parse_args()

    if args.list:
        plans = list_plans(args.vault)
        if not plans:
            print("No plans found in Plans/")
        else:
            print(f"Plans ({len(plans)}):")
            for p in plans:
                print(f"  {p.name}")
        sys.exit(0)

    if args.source:
        try:
            task_data    = load_task_from_file(args.source)
            description  = task_data["description"]
            source_file  = args.source
            print(f"Loaded task from: {args.source}")
            print(f"Description     : {description[:100]}")
        except FileNotFoundError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
    else:
        description = args.task
        source_file = None

    plan_path = create_plan(
        task_description=description,
        vault_path=args.vault,
        source_file=source_file,
    )
    print(f"\nPlan created: {plan_path}")
    print(f"Open it in Obsidian or any Markdown editor to view and edit.")
