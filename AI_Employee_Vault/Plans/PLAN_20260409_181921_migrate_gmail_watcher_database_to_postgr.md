---
type: plan
status: active
created: 2026-04-09T18:19:21
complexity: high
domain: database
total_estimate: "4–8 hours (may span multiple sessions)"
steps_count: 9
---

# Plan: Migrate Gmail watcher database to PostgreSQL and add full-text search

**Created:** 2026-04-09T18:19:21  
**Complexity:** High  
**Domain:** Database  
**Total estimate:** 4–8 hours (may span multiple sessions)  
**Steps:** 9

---

## Task Description

Migrate Gmail watcher database to PostgreSQL and add full-text search

---

## Resources Needed

- [ ] Access to the vault (AI_Employee_Vault/)
- [ ] Project repository access
- [ ] Relevant documentation or specs
- [ ] Database credentials and connection string
- [ ] Database client (psql, DBeaver, etc.)
- [ ] Backup storage location

---

## Steps

### Step 1: Understand and scope the task

Re-read the full task description. Clarify any ambiguities with the stakeholder. Identify what is explicitly in-scope and what is out-of-scope. Confirm the definition of done.

- **Estimate:** 15–30 min
- **Depends on:** None
- [ ] Complete

### Step 2: Gather requirements and resources

List all inputs, credentials, access rights, external systems, and documentation needed. Identify blockers and resolve them before proceeding to implementation.

- **Estimate:** 15–30 min
- **Depends on:** Step 1
- [ ] Complete

### Step 3: Design schema changes

Define the target schema. List all tables, columns, indexes, and constraints being added or modified. Write the migration script.

- **Estimate:** 30–60 min
- **Depends on:** Step 2
- [ ] Complete

### Step 4: Back up existing data

Take a full database backup. Verify the backup can be restored. Store the backup file in a safe location.

- **Estimate:** 15–30 min
- **Depends on:** Step 3
- [ ] Complete

### Step 5: Apply migration in staging

Run the migration script against a staging environment. Verify row counts, constraints, and application behaviour.

- **Estimate:** 30–60 min
- **Depends on:** Step 4
- [ ] Complete

### Step 6: Apply migration in production

Schedule a maintenance window if needed. Run migration script. Monitor logs for errors. Verify application is healthy.

- **Estimate:** 30–60 min
- **Depends on:** Step 5
- [ ] Complete

### Step 7: Risk assessment and rollback plan

Identify the top 3 risks (probability × impact). Define a rollback procedure for each risk. Document the rollback steps before proceeding.

- **Estimate:** 30–60 min
- **Depends on:** Step 6
- [ ] Complete

### Step 8: Test and validate

Run all relevant tests. Verify the outcome matches the success criteria defined in this plan. Check edge cases. Document any deviations.

- **Estimate:** 30–60 min
- **Depends on:** Step 7
- [ ] Complete

### Step 9: Document and close

Update any relevant README, runbook, or Dashboard. Archive this plan to Done/. Notify stakeholders of completion.

- **Estimate:** 15–30 min
- **Depends on:** Step 8
- [ ] Complete

---

## Success Criteria

- [ ] All planned steps are completed and checked off
- [ ] No critical errors or regressions introduced
- [ ] Outcome is reviewed and accepted by the stakeholder
- [ ] This plan file is moved to Done/ and Dashboard is updated
- [ ] Migration applied cleanly in production with zero data loss
- [ ] All application queries return correct results post-migration

---

## Notes

_Add implementation notes, blockers, and decisions here as you work through the plan._
