# Mandate 28 design review

- Reviewed: 2026-07-30
- Input: `C:\Users\LENOVO\Downloads\mandate28.md`
- Decision: **APPROVED WITH CORRECTIONS**
- Implementation branch: `feat/mandate28-frozen-baseline`

## Findings resolved before implementation

### 1. Alert-state vocabulary was incomplete

The design requires an alert-state record for every replay step, including
healthy normal traffic and legitimate load shifts, but the proposed list did
not include states for either case. The implementation adds `NORMAL` and
`INFO_LOAD_SHIFT`. Without these states the alert stream would have deliberate
gaps or would mislabel healthy traffic as suppressed incidents.

### 2. Replay persistence is not production persistence

The design correctly rejects reuse of `valkey-cart`. The implementation
provides a state-version CAS Valkey adapter and pins the already-used repository
Redis client version, but the replay uses a deterministic in-memory CAS store.
A dedicated `noeviction` AIOps Valkey with AOF/RDB is therefore a deployment
gate, not a result claimed by this change.

### 3. Recovery contract is isolated from the current IncidentStore

Mandate 28 deliberately requires two `RECOVERING` observations and resolves on
the third healthy poll. The current runtime IncidentStore default uses two
polls. This implementation keeps the new three-poll rule inside the Mandate 28
lifecycle engine and does not silently change existing Mandate 22 remediation
semantics before runtime integration is approved.

## Accepted architecture

The key is exactly
`environment::namespace::service::incident_type`. The stored frozen baseline
contains every clean raw point plus median and MAD. Active observations never
enter that baseline. State writes compare `state_version`; Valkey uses one Lua
CAS operation and a bounded engine retry. A stale/equal observation sequence is
idempotently suppressed instead of creating a second incident.

Primary telemetry loss and insufficient traffic update data quality but cannot
advance recovery. Missing logs/traces set `enrichment_degraded` without stopping
primary detection. Recovery flapping returns to `ACTIVE_SUSTAINED`, resets the
healthy streak and retains the incident ID/baseline.

## Trade-offs

- The raw frozen window costs more state than storing aggregates, but it is
  necessary to reproduce Median/MAD, ratio, z-score, EWMA and trend decisions.
- Three healthy observations delay resolution but make the flapping rule
  deterministic and reviewable.
- Lua CAS is atomic and compact, but production correctness still depends on a
  dedicated durable Valkey failure boundary.
- Runtime integration is intentionally separate from replay evidence so a
  passing simulator cannot alter existing detector/remediation behavior.

## Claim boundary

This change proves the deterministic lifecycle and replay contract at evidence
level 3. It does not prove production Valkey durability, live Prometheus
coverage, production restart recovery, alert delivery or deployment acceptance.
It does not change SLO/error budgets or any `flagd` file.
