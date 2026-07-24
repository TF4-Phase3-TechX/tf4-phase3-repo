# Prometheus memory-headroom mitigation — 2026-07-24

## Purpose and owner

AIO owns this bounded mitigation because Prometheus continuity is a
prerequisite for the Mandate 7b/15 detector drills. The shared observability
owner must review the resource change because Prometheus runs in
`techx-observability`.

## Runtime observation

Read-only inspection through the production AIOps-to-Prometheus path found:

- `prometheus-server` request/limit: `1Gi/1Gi`;
- nine container restarts;
- last termination: `OOMKilled` at `2026-07-24T08:38:41Z`;
- maximum 30-minute working set at the preflight:
  `966004736` bytes (about 921 MiB);
- 17 `up` series each had 30 samples in the inspected 30-minute window;
- no additional restart was observed by `2026-07-24T13:39Z`.

The node hosting Prometheus had a 6-hour peak usage of 57.18% and minimum
available memory of 4.24 GiB. Its active requested memory was 3.03 GiB. Raising
only the container limit does not change the scheduler request.

## Decision

- Keep the Prometheus memory request at `1Gi`.
- Increase the Prometheus memory limit from `1Gi` to `2Gi`.
- Keep the existing seven-day TSDB retention for this change.
- Do not combine cardinality, ingestion or retention tuning with the immediate
  drill-unblocking mitigation.

This creates failure headroom without changing pod scheduling or deleting
recent detector evidence. It is a mitigation for the observed ceiling, not a
claim that telemetry ingestion has been fully tuned.

## Trade-off and failure mode

A higher limit allows Prometheus to consume up to one additional GiB on its
node. Node headroom supports that envelope at the observed load, but an
unbounded cardinality or ingestion increase can still consume the new limit.
If memory continues to trend upward, investigate active series, label
cardinality, OTLP ingestion, query load and retention before increasing the
limit again.

## Rollout acceptance and rollback

After GitOps reconciliation, observe for 30–60 minutes:

- pod Ready with no new restart or `OOMKilled`;
- effective `prometheus-server` limit is `2Gi`;
- continuous scrapes for detector-critical targets;
- working set remains below the new ceiling without monotonic growth;
- AIOps records no Prometheus polling degradation.

Abort the load drill and roll back the resource change if the pod cannot
schedule, the node experiences memory pressure, scrape continuity degrades, or
Prometheus restarts.

## Claim boundary

At authoring time the evidence level is 2–3: the mitigation is implemented in
configuration and the decision is backed by read-only runtime measurements.
It is not deployed, runtime-verified or accepted until the rollout criteria
above are observed.
