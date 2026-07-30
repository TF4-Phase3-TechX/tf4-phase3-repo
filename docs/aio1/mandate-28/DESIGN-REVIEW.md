# Mandate 28 design review

- Reviewed: 2026-07-30
- Input: `C:\Users\LENOVO\Downloads\mandate28.md`
- Decision: **APPROVED WITH CORRECTIONS IMPLEMENTED**
- Implementation branch: `feat/mandate28-frozen-baseline`

## Corrected architecture

The state key is exactly
`environment::namespace::service::incident_type`. Frozen state retains every
candidate raw point and a true Median/MAD-filtered clean view. Active incident
points never enter that baseline. Slow drift uses a fitted least-squares slope
consistent with the runtime detector. Missing SLO burn telemetry cannot hide an
independently observed error storm.

State writes compare `state_version`; Valkey uses one Lua CAS operation and a
bounded retry. Event IDs provide idempotence, while a durable timestamp
high-water mark rejects late data without treating a producer sequence reset as
stale. UUIDv5 incident IDs include the composite key, timestamp and event ID.
Resolved incident metadata is retained when the same key later opens a new
incident.

Evidence is a bounded 64-sample tail with a rolling SHA-256 digest and total
count. Restart replay serializes and reloads state instead of reusing the same
Python object. Primary telemetry loss and insufficient traffic hold lifecycle;
missing enrichment never stops primary detection.

The scenario generator, detector and oracle are separate. Strict input models
forbid detector labels in raw scenario rows. The same service experiences
varying traffic during Incident A. Two distinct observations race the same
state version, and both event IDs survive the CAS retry path.

Protected `flagd` and SLO inputs are verified before and after replay using a
committed SHA-256 manifest. The generated verdict is explicitly a candidate;
the independent reviewer name, reviewed commit SHA and conclusion remain empty
until a reviewer supplies them.

## Claim boundary

This change proves deterministic lifecycle and replay behavior at evidence
level 3. It does not prove production Valkey durability, live Prometheus
coverage, production restart recovery, alert delivery or deployment acceptance.
