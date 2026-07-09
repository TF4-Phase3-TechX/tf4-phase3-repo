# Audit Runbooks

This folder stores real operational runbooks for auditability workflows.

Use `../templates/RUNBOOK_TEMPLATE.md` when creating a runbook.

## Naming

- `<system-or-process>-<action>.md`

## When To Create A Runbook

- The action is repeatable and operational.
- A reviewer or on-call person must follow the same process later.
- The process captures evidence, verifies logs, checks alerts, or responds to an auditability incident.

## Minimum Content

- Owner and escalation path
- Prerequisites
- Step-by-step procedure
- Rollback or stop conditions
- Evidence to capture
