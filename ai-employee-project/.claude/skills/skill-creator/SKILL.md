---
name: skill-creator
description: "Creates new Agent Skills following best practices and standards"
triggers:
  - create skill
  - make new skill
  - generate skill
  - add skill
---

# Skill: skill-creator

Creates new Agent Skills as pure markdown instruction files. Ensures every
generated skill follows the standard template, passes the validation checklist,
and is saved to the correct location.

---

## Purpose

This skill is the single source of truth for how all other skills in this
project are created. It enforces consistency: every skill is a set of plain
English instructions that tell Claude what to do and which Python files to call
— never implementation code.

---

## Process

When this skill is invoked, follow these steps in order:

### Step 1 — Gather information

Ask the user for:

1. **Skill name** — lowercase, hyphenated (e.g. `calendar-check`, `slack-notify`)
2. **One-line description** — what does this skill do in plain English?
3. **Trigger phrases** — 2–4 phrases a user might say to invoke this skill
4. **What it monitors or acts on** — file system, API, vault, external service?
5. **Python module it uses** — which file in `watchers/` or `helpers/` provides the logic? (If none yet, note that one needs to be created.)
6. **Expected input** — what does the skill receive or look for?
7. **Expected output** — what files does it create, where, in what format?

Do not proceed to Step 2 until all seven questions are answered.

---

### Step 2 — Generate the skill file

Using the answers from Step 1, produce a `SKILL.md` with the following sections
in this exact order:

#### 2a. Frontmatter

```
---
name: <skill-name>
description: "<one-line description>"
triggers:
  - <trigger phrase 1>
  - <trigger phrase 2>
  - <trigger phrase 3>
config:
  <any relevant config keys and their default values>
---
```

#### 2b. Title and summary

```
# Skill: <skill-name>

<2–3 sentence plain-English summary of what this skill does and why.>
```

#### 2c. Purpose section

Explain the business reason for this skill in 3–5 bullet points. Answer: why does this exist? What problem does it solve?

#### 2d. Process section

Numbered list of every step that happens when the skill runs:

1. What it reads or connects to
2. What it filters or queries
3. What it creates (vault cards, log entries, etc.)
4. What follow-up skills it calls (always call `update-dashboard` if vault cards are created)

#### 2e. How to Run section

Specify the exact Python module and class/function to call:

- Project root path
- Module path (e.g. `watchers.my_watcher`)
- Class name and constructor arguments
- Methods to call in order
- What to do with the return value

Do **not** write Python code. Write it as a description with a reference block like:

```
Module:  watchers.my_watcher
Class:   MyWatcher(vault_path, ...)
Methods: check_for_updates() → list of dicts
         create_action_file(item) → Path
```

#### 2f. Output — Vault Card Format section

Show the YAML frontmatter of the card the skill produces. Include all fields.
Add a **Priority rules** sub-section if the skill sets a priority field.

#### 2g. Expected Output section

Show two terminal output examples:
- One where items are found
- One where nothing is found

#### 2h. Dependencies section

List:
- Python files in `watchers/` or `helpers/` that must exist
- Any external APIs or credentials required
- Any vault folders that must exist

#### 2i. Notes section

Any edge cases, error handling behaviour, or operational notes worth knowing.

---

### Step 3 — Validate against checklist

Before saving, verify every item in this checklist is satisfied:

**Structure**
- [ ] Frontmatter has `name`, `description`, and at least 2 `triggers`
- [ ] All required sections are present (Purpose, Process, How to Run, Output, Expected Output, Dependencies, Notes)
- [ ] Sections are in the correct order

**Content**
- [ ] No Python code blocks anywhere in the file
- [ ] No implementation details (no regex, no loops, no conditionals written as code)
- [ ] Instructions are written in plain English
- [ ] The How to Run section references an actual file in `watchers/` or `helpers/`
- [ ] Expected Output section contains at least two examples

**Conventions**
- [ ] Skill name is lowercase and hyphenated
- [ ] File will be saved to `.claude/skills/<skill-name>/SKILL.md`
- [ ] Description is under 80 characters
- [ ] Trigger phrases are 2–5 words each

If any item fails, fix it before saving.

---

### Step 4 — Save the file

Save the completed skill to:

```
.claude/skills/<skill-name>/SKILL.md
```

Create the directory if it does not exist. Do not create any other files.

Confirm to the user:
- Full path where the file was saved
- Checklist pass/fail summary
- Whether a corresponding Python file in `watchers/` or `helpers/` still needs to be created

---

## Usage Examples

**User says:** "Create a skill that monitors a Slack channel for mentions"

Expected flow:
1. Claude asks the 7 questions from Step 1
2. User answers: name=`slack-monitor`, triggers=`check slack / monitor slack`, module=`watchers.slack_watcher`, etc.
3. Claude generates the full `SKILL.md` using the template
4. Claude validates against the checklist
5. Claude saves to `.claude/skills/slack-monitor/SKILL.md`
6. Claude notes that `watchers/slack_watcher.py` still needs to be created

---

**User says:** "Make a new skill for checking calendar events"

Expected flow:
1. Claude asks the 7 questions
2. Generates `SKILL.md` for `calendar-check`
3. Validates — no Python code, all sections present
4. Saves to `.claude/skills/calendar-check/SKILL.md`

---

## Dependencies

- No Python files required — this skill operates entirely through Claude's file tools
- All other skills it creates may require files in `watchers/` or `helpers/`
- The `.claude/skills/` directory must exist (it does by convention in this project)

---

## Notes

- This skill follows its own template — it is an example of the standard it enforces
- If the user wants to create a skill that requires new Python logic, note which file needs to be created but do not create it as part of this skill — that is a separate task
- Never embed Python in a skill file, even as a "quick example" — use a reference block instead
- If a skill already exists at the target path, ask the user before overwriting
- Skill names must be unique within `.claude/skills/`
