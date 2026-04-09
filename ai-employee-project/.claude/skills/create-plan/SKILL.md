---
name: create-plan
description: "Generate structured action plans for complex multi-step tasks."
tier: silver
triggers:
  - "create plan for"
  - "plan for task"
  - "break down this task"
  - "how should I approach"
  - "plan this project"
  - "create action plan"
config:
  vault_path: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
  log_file: "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/ai-employee-project/logs/plans_created.log"
  plans_folder: "Plans"
  source_folder: "Needs_Action"
---

# Skill: create-plan

This skill takes a task description from the user or from an existing Needs_Action/
vault card, assesses whether the task is complex enough to need a plan, then
calls `helpers/plan_creator.py` to generate a structured `PLAN_<timestamp>_<slug>.md`
file saved to `Plans/`. Simple single-step tasks are redirected to Needs_Action/
rather than receiving a full plan.

---

## Purpose

- Replace informal ad-hoc thinking with a reusable, structured plan document
  that can be tracked, updated, and referenced across sessions
- Automatically detect task domain (database, api, email, security, etc.) and
  apply domain-specific step templates — no manual template selection needed
- Close the loop between incoming task cards (`Needs_Action/`) and their plans
  by writing a back-link into the original card
- Keep the Dashboard and log file current so the user always knows how many
  plans are active and when they were created
- Guide the user to avoid over-planning: single-action tasks are identified and
  redirected rather than given unnecessary structure

---

## Process

### Step 1 — Identify the task source

**Option A — User input:**
Extract everything after the trigger phrase as the task description.

If the description is fewer than 10 words or is ambiguous (e.g. "plan this"),
ask before proceeding:
> "Can you describe the task in more detail? What is the goal and what does
> 'done' look like?"

**Option B — From a Needs_Action/ file:**
If the user references a specific file (e.g. "create plan for this task —
`Needs_Action/GMAIL_20260409_123000.md`"), call `load_task_from_file()` to
extract the description from that card's frontmatter and body.

Confirm before proceeding:
> "I'll create a plan for: '<extracted description>'. Proceed?"

**Option C — List existing plans:**
If the user says "show my plans", "list plans", or "what plans exist", call
`list_plans(vault_path)` and display the results without generating a new plan.

### Step 2 — Assess complexity

Before generating a plan, determine whether the task warrants one.

**Create a plan** if any of the following are true:
- The task has 3 or more distinct steps
- Estimated time is more than 1 hour
- Multiple people, systems, or services are involved
- Steps have dependencies on each other
- The task has deliverables, approvals, or review requirements
- The work spans more than one day or session

**Skip the plan** if all of the following are true:
- Single clear action (reply to an email, run tests, make a call)
- Under 1 hour with no dependencies
- No coordination or approval required

When skipping, say:
> "This looks like a simple task — no detailed plan needed.
> Would you like me to add it to Needs_Action/ as a quick task instead?"

### Step 3 — Generate the plan

Call `helpers/plan_creator.py` → `create_plan()` with the collected inputs.

`create_plan()` handles all internal analysis automatically:
- Detects complexity level (low / medium / high) from keyword analysis
- Identifies the primary domain (database, api, email, linkedin, security, etc.)
- Selects domain-specific step templates with per-step time estimates
- Adds a risk assessment step for high-complexity tasks
- Builds a domain-specific success criteria checklist
- Lists required resources (credentials, tools, access)
- Renders the full Plan.md with YAML frontmatter
- Writes `PLAN_<timestamp>_<slug>.md` to `Plans/`
- Updates Dashboard activity internally
- Returns the absolute Path of the created file

### Step 4 — Link plan to source task (if from Needs_Action/ file)

If the plan was triggered from a Needs_Action/ card (Option B in Step 1),
append the following section to the end of that original card:

```
## Plan Created

A detailed plan has been generated for this task.

**Plan file:** Plans/<PLAN_filename>
**Created:** <ISO timestamp>
**Complexity:** <low | medium | high>

See the plan file for step-by-step breakdown, time estimates, and success criteria.
```

### Step 5 — Log plan creation

Append one line to `logs/plans_created.log` in the project root:

```
[<timestamp>] CREATED | Task: <first 60 chars of description> | File: <plan filename> | Steps: <N>
```

If the log file or `logs/` directory does not exist, create them. If the write
fails for any reason, continue without logging — this is non-fatal.

### Step 6 — Update Dashboard

The Dashboard activity entry is written automatically inside `create_plan()`.
After the call returns, also increment the Plans Created counter:
- Activity: `"Plan created: <task description (first 60 chars)>"`
- Stat: increment `plans_created` by 1

### Step 7 — Report to user

```
Plan created successfully!
  File:       Plans/<PLAN_filename>
  Steps:      <N> steps identified
  Complexity: <low | medium | high>
  Domain:     <detected domain>
  Estimate:   <total time estimate>

Open the plan in Obsidian or any Markdown editor to review and start working.
```

If triggered from a Needs_Action/ file (Step 4 was executed), add:
```
Original task updated: Needs_Action/<source_filename> now links to the plan.
```

---

## How to Run

Three functions from `helpers/plan_creator.py` are used depending on context.

```
Module:   helpers.plan_creator

Function 1 — generate plan (Step 3):
  create_plan(task_description, vault_path, source_file=None)
  Arguments:
    task_description — free-text task description string
    vault_path       — from config.vault_path
    source_file      — optional: absolute path to the Needs_Action/ card (str or Path)
  Returns: Path — absolute path of the created PLAN_<timestamp>_<slug>.md file
  Side effects: writes Plans/<file>, updates Dashboard activity

Function 2 — parse source card (Step 1, Option B):
  load_task_from_file(file_path)
  Arguments:
    file_path — path to any vault card (.md file)
  Returns dict:
    description  (str)  — best task description extracted from frontmatter or body
    source_type  (str)  — 'email' | 'linkedin' | 'file' | 'unknown'
    raw_content  (str)  — full file text

Function 3 — list existing plans (Step 1, Option C):
  list_plans(vault_path)
  Arguments:
    vault_path — from config.vault_path
  Returns: list[Path] — PLAN_*.md files in Plans/, newest first
```

---

## Output — Vault Card Format

Plan file written to `Plans/PLAN_<timestamp>_<slug>.md`:

```yaml
---
type: plan
status: active
created: 2026-04-09T16:30:00
complexity: high
domain: database
total_estimate: "4–8 hours (may span multiple sessions)"
steps_count: 9
---
```

The file body contains six sections in this order:

| Section | Content |
|---|---|
| `## Task Description` | Full task description verbatim |
| `## Resources Needed` | Domain-specific checklist (credentials, tools, access) |
| `## Steps` | Numbered steps, each with title, detail, estimate, dependency, `[ ]` checkbox |
| `## Success Criteria` | Base + domain-specific measurable checklist |
| `## Notes` | Empty — filled in by the user during execution |

Step entry format within `## Steps`:

```
### Step N: <title>

<detail paragraph>

- **Estimate:** <time range>
- **Depends on:** Step N-1 (or None)
- [ ] Complete
```

### Priority rules

The `complexity` frontmatter field is set automatically by `create_plan()`:

| Value | Triggered when |
|---|---|
| `low` | Task keywords match fix / patch / rename / tweak, or description < 10 words |
| `medium` | Task keywords match implement / build / update / develop, or 10–30 words |
| `high` | Task keywords match migrate / architecture / deploy / security, or > 30 words |

High-complexity plans receive an additional **Risk assessment and rollback plan**
step injected before the test/validate step.

---

## Expected Output

**Plan created from user input:**

```
Plan created successfully!
  File:       Plans/PLAN_20260409_163000_launch_new_product_website.md
  Steps:      8 steps identified
  Complexity: high
  Domain:     frontend
  Estimate:   4–8 hours (may span multiple sessions)

Open the plan in Obsidian or any Markdown editor to review and start working.
```

**Plan created from Needs_Action/ card:**

```
Plan created successfully!
  File:       Plans/PLAN_20260409_163100_migrate_database_to_postgresql.md
  Steps:      9 steps identified
  Complexity: high
  Domain:     database
  Estimate:   4–8 hours (may span multiple sessions)

Original task updated: Needs_Action/GMAIL_20260409_123000.md now links to the plan.
```

**Simple task — plan skipped:**

```
This looks like a simple task — no detailed plan needed.
Would you like me to add it to Needs_Action/ as a quick task instead?
```

**List existing plans:**

```
Existing plans (3):
  PLAN_20260409_163100_migrate_database_to_postgresql.md  (2026-04-09)
  PLAN_20260408_091500_onboard_new_client.md              (2026-04-08)
  PLAN_20260407_143000_build_reporting_dashboard.md       (2026-04-07)
```

**Source file not found:**

```
Task file not found: Needs_Action/GMAIL_20260409_123000.md
Please provide the full path to the Needs_Action/ card and try again.
```

---

## Dependencies

Python files that must exist:
- `helpers/plan_creator.py` — `create_plan()`, `load_task_from_file()`, `list_plans()`
- `helpers/dashboard_updater.py` — activity logging and stat updates

Vault folders (created automatically if absent):
- `AI_Employee_Vault/Plans/` — destination for all plan files (created by `create_plan()`)
- `AI_Employee_Vault/Needs_Action/` — source for file-based plan triggers
- `AI_Employee_Vault/Done/` — destination when a plan is completed and archived

Log file (created automatically):
- `logs/plans_created.log` — project root
  Format: `[timestamp] CREATED | Task: <60 chars> | File: <name> | Steps: <N>`

No external APIs or credentials required — all processing is local.

---

## Notes

- `create_plan()` handles domain detection, step template selection, and
  Dashboard activity internally — the skill does not need to pass domain or
  complexity explicitly.
- When linking back to a source Needs_Action/ card (Step 4), append the
  `## Plan Created` section at the end of the file — do not modify existing content.
- If the user says "list plans" or "show my plans" without providing a task,
  call `list_plans()` and return the file names — do not ask for a task description.
- The `Plans/` folder may already exist and contain other plans from earlier sessions.
  `create_plan()` uses a timestamp slug to avoid collisions — never overwrite.
- When a plan is complete, the user should move the plan file from `Plans/` to
  `Done/` manually (or via the `process-inbox` skill). The plan's `status` frontmatter
  should be updated to `completed` at that point.
- Log write failures are non-fatal — if `logs/plans_created.log` cannot be written
  (e.g. permissions issue), report the error as a warning and continue.
- If `helpers/plan_creator.py` is missing, report:
  "Plan creator not installed. Ensure `helpers/plan_creator.py` exists in the project."
