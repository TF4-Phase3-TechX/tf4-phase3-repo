# D5-PERF-05 precheck verdict

**Verdict:** **BLOCKED - DO NOT START LOAD**

## Blocking reasons

- Resource remediation does not have a PASS verdict.
- An absolute UTC approved change window was not provided.
- Admission evidence indicates that resource enforcement is not active.

## Operator action

This script never starts Locust and never restarts a workload. When PASS, use
the single approved Locust UI harness described in
`docs/evidence/directive-05/D5-PERF-05-performance-regression-contract.md`.
