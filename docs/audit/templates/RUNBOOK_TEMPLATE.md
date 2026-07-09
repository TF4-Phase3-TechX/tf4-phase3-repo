# Runbook: <Service/Scenario>

Owner: <team/person>
Last updated: YYYY-MM-DD
Related SLO: <SLO or N/A>
Related dashboard: <link or path>
Related Jira: <SCRUM-xxx or N/A>

## Purpose

<Describe when to use this runbook.>

## Symptoms

- <Observable symptom>
- <Alert/log/metric signal>
- <Customer or business impact>

## First Checks

```powershell
<command 1>
<command 2>
```

## Investigation Steps

1. <Check current status and scope.>
2. <Confirm impact with metrics/logs/traces.>
3. <Collect evidence before making changes.>
4. <Identify likely owner/escalation path.>

## Mitigation

<Describe safe mitigation steps. Do not bypass protected flagd/OpenFeature incident mechanisms.>

## Escalation

- Primary owner: <team/person>
- Backup: <team/person>
- Escalate when: <condition>

## Evidence To Capture

- Timestamp and timezone.
- Commands and output summary.
- Screenshot/log/query link.
- Affected services/users/SLO.
- Related PR/Jira/ADR links.

## Rollback

<Describe rollback for any config/deploy change.>

## Follow-up

- <Action item>
- <Owner>
- <Due date>
