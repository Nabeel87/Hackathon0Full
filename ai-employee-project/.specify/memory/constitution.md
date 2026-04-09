<!--
SYNC IMPACT REPORT
==================
Version change: [TEMPLATE] → 1.0.0 (initial ratification — no prior version)
Modified principles: N/A (first fill)
Added sections:
  - Core Principles (6 principles)
  - Security Constraints
  - Development Workflow
  - Governance
Removed sections: N/A
Templates checked:
  ✅ .specify/templates/plan-template.md — Constitution Check gate references principles; compatible
  ✅ .specify/templates/spec-template.md — FR/SC format; no principle conflicts
  ✅ .specify/templates/tasks-template.md — Phase structure; no principle conflicts
  ✅ .specify/templates/phr-template.prompt.md — PHR routing; no conflicts
Deferred items: None
-->

# AI Employee Constitution

## Core Principles

### I. Privacy-First (NON-NEGOTIABLE)
The system MUST never read file contents or email bodies.
Stored metadata is limited to: filename, size, extension, timestamp (files);
sender, subject, 200-char snippet (emails).
The security blacklist (`.ssh`, `.config`, `.env`, `credentials`, `passwords`,
`secret`, `private_key`, `id_rsa`, `.pem`, `.p12`, `.pfx`) MUST be enforced
before any file is processed — no exceptions, no overrides.
Hidden files (`.`-prefix) and lock files (`~`-prefix, `.tmp`, `.part`) MUST be
silently skipped.

**Rationale**: The system operates on behalf of the user inside their personal
environment. Any breach of file privacy would make it untrustworthy and
potentially expose credentials or personal data.

### II. Local-Only Processing
All data storage and processing MUST occur on the local machine.
No user data, vault contents, or credentials MAY be transmitted to external
services. The sole permitted external call is the Gmail read-only API using
OAuth2 (`gmail.readonly` scope — cannot send, delete, or modify email).
Credentials (`credentials.json`, `token.json`) MUST remain in `.credentials/`
and MUST be git-ignored.

**Rationale**: Zero cloud infrastructure is a core design goal. The system MUST
be fully operational without internet access except for Gmail polling.

### III. Vault-Driven Workflow
Every detected item MUST produce a structured Markdown card in `Vault/Inbox/`.
Cards MUST include YAML frontmatter with `type`, `status: pending`, `priority`,
and detection timestamp.
The routing pipeline is strictly `Inbox/ → Needs_Action/ → Done/` — no
skipping stages. Cards MUST be moved atomically (conflict-safe rename); no
in-place editing of routed cards.
`Dashboard.md` MUST be updated after every watcher cycle.

**Rationale**: The vault is the single source of truth for all work items.
Consistent card format enables reliable automation at every tier.

### IV. Watcher-Based Monitoring
All monitoring MUST inherit from `BaseWatcher` (ABC) and implement
`check_for_updates()` and `create_action_file()`.
Watchers MUST use polling (not filesystem events) to remain simple, portable,
and thread-safe.
Each watcher MUST run in its own `WatcherThread` with independent restart
capability. The orchestrator (`main.py`) MUST handle `SIGINT`/`SIGTERM`
gracefully, draining active cycles before exit.
Deduplication MUST be enforced: already-logged items MUST never produce
duplicate cards within a session or across sessions.

**Rationale**: The polling model is simpler, more predictable, and avoids
platform-specific filesystem event APIs. Clean shutdown prevents data loss.

### V. Agent Skill Layer
Every user-facing capability MUST be exposed as a plain-Markdown Agent Skill
(`SKILL.md`) with natural-language trigger phrases — no commands to memorise.
Skills MUST NOT contain Python code blocks; they delegate to the Python layer.
Each skill MUST have: YAML frontmatter (`name`, `description`, `triggers`),
a Purpose section, a Process section, and a Usage section.
New skills MUST be created via the `skill-creator` meta-skill to enforce
the standard template and 15-item validation checklist.

**Rationale**: The Skill layer decouples user intent from implementation.
Users interact in natural language; the Python layer handles all I/O.

### VI. Observable State
`Dashboard.md` is the live system view and MUST always reflect current state.
It MUST contain four sections: System Status table, Quick Stats, Recent
Activity log (newest-first), and Current Alerts.
All component status changes MUST be written to the dashboard immediately —
never deferred. Vault folder counts MUST be re-synced after every
`process-inbox` run.
Log files (`logs/main.log`) MUST capture all watcher events with UTC timestamps.

**Rationale**: Without a reliable dashboard, the system is a black box.
Observable state is mandatory for debugging, auditing, and user trust.

---

## Security Constraints

- Secrets and credentials MUST never be committed to git (enforced via `.gitignore`).
- The Gmail OAuth scope is permanently locked to `gmail.readonly`; MUST NOT be
  expanded without a Governance amendment.
- File size and extension metadata are stored; file binary contents are NEVER
  read or stored.
- All card filenames are slugified and length-capped to prevent path injection.
- No subprocess execution of detected files is permitted at any tier.

---

## Development Workflow

- **Tier progression**: Bronze → Silver → Gold. Each tier MUST be formally
  complete (all deliverables, tests passing, git tag applied) before Silver
  work begins.
- **Smallest viable diff**: PRs MUST not include unrelated refactors.
  Complexity MUST be justified in `plan.md`.
- **Test-first for new watchers**: Any new watcher MUST have integration tests
  that exercise the full `Inbox → Done` path before merging.
- **PHR required**: Every significant prompt session MUST produce a Prompt
  History Record under `history/prompts/`.
- **No hardcoded paths in library code**: Paths MUST be passed as parameters
  or resolved at runtime relative to a configurable root. The only exception
  is standalone `__main__` entry points.

---

## Governance

This constitution supersedes all other project practices where conflicts arise.
Amendments require:
1. A documented rationale (PR description or ADR).
2. Version increment per semantic versioning rules defined in the SDD toolchain.
3. A consistency propagation pass across all `.specify/templates/` files.
4. Update of `LAST_AMENDED_DATE` and `CONSTITUTION_VERSION`.

All PRs MUST include a Constitution Check (see `plan-template.md`) before
Phase 0 research begins.

**Version**: 1.0.0 | **Ratified**: 2026-04-06 | **Last Amended**: 2026-04-09
