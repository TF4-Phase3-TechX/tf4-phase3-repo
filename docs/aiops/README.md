# TF4 AI Ops Safe MVP

The `aiops` service continuously reads TF4 telemetry and turns sustained anomalies into auditable incidents. It implements the first two agreed incident families: LLM timeout/error and service latency spike.

## Runtime flow

```text
Prometheus metrics -----+
OpenSearch logs --------+--> sustained detector --> evidence correlation
Jaeger traces ----------+                         --> deterministic RCA
                                                  --> allowlisted runbook
                                                  --> Prometheus event counter
                                                  --> Alertmanager Slack/email
                                                  --> per-incident approval
                                                  --> dry-run/live action
                                                  --> rollout + SLO verification
                                                  --> resolve or restore/escalate
```

Prometheus is the primary detector. Logs and traces increase confidence and provide investigation references. Prometheus scrapes the worker's `/metrics` endpoint; a newly created, cooldown-deduplicated incident increments a severity-labelled counter, and the committed `AIOpsIncidentDetected` rule routes it through the existing Alertmanager Slack/email receivers. The service never mutates flagd. LLM output is not allowed to select or execute an action.

The design decision, initial three-signal baseline analysis, trade-offs and activation boundary are recorded in [ADR-007](./ADR-007-hybrid-anomaly-detection-and-safe-response.md).

## Run locally

```bash
cd techx-corp-platform
docker compose up --build aiops prometheus opensearch jaeger
curl http://localhost:8088/healthz
curl http://localhost:8088/v1/incidents
```

Approve a dry-run action:

```bash
curl -X POST http://localhost:8088/v1/incidents/INCIDENT_ID/approve \
  -H "Authorization: Bearer local-demo-token"
```

## Safety defaults

- `REMEDIATION_MODE=dry-run`; live Kubernetes mutation must be explicitly enabled.
- Every action requires a non-expired approval for that incident.
- Only allowlisted Deployments can be targeted.
- One action can run per target; arbitrary commands and flagd mutation are unsupported.
- A live rollback is successful only when the Deployment is ready, target p95 recovers, and checkout/storefront error rate stays below 1%.
- Failed verification restores the original pod template and escalates.

Create the approval Secret before deploying if the API will be used:

```bash
kubectl -n techx-corp create secret generic aiops-approval-token \
  --from-literal=token='REPLACE_WITH_A_LONG_RANDOM_TOKEN'
```

For a controlled live drill, CDO must first confirm the namespace, Deployment allowlist, known-good ReplicaSet, drill window, SLO queries and rollback owner. Then set both the component environment `REMEDIATION_MODE=live` and Helm value `aiopsRemediation.liveEnabled=true` through a reviewed values file. The latter is what grants `patch` permission; dry-run deployments only receive read access. Do not use live mode against an unapproved incident.

## Interfaces

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Process health |
| GET | `/readyz` | Worker readiness |
| GET | `/metrics` | Service metrics for Prometheus |
| GET | `/v1/telemetry/status` | Read-only Prometheus/OpenSearch/Jaeger connectivity probe |
| GET | `/v1/incidents` | Recent bounded incident list |
| GET | `/v1/incidents/{id}` | Evidence, RCA and audit trail |
| GET | `/v1/incidents/{id}/summary` | Operator Markdown with exact queries and encoded Grafana Explore link |
| POST | `/v1/incidents/{id}/approve` | Approve and execute the bound action |
| POST | `/v1/incidents/{id}/reject` | Reject the action |

The incident store is intentionally bounded and in-memory for the first MVP. Structured incident/audit events are also written to stdout for collection into OpenSearch. Alertmanager notification is wired through `aiops_incidents_created_total`; persistent state and automatic Jira creation remain follow-up work.

The unavailable-source semantics, production `app_llm_*` metric correction and operator summary concepts from the team's [PR #208](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208) are consolidated into this service. The old prototype tree is not duplicated as a second runtime.

## SOTA-lite scoring and offline benchmark

The runtime keeps the team's research-inspired approach without claiming a
paper reproduction:

- **BARO-lite:** dynamic per-service baseline, ratio/z-score/EWMA and Isolation
  Forest evidence for sustained metric anomalies.
- **TORAI-lite:** normalized metric/log/trace/deployment/AI evidence weights,
  with missing sources reported and excluded from the denominator.

The deterministic offline BARO-lite service-localization benchmark was run on
a 60-case RCAEval-v2 sample stratified across three systems and all available
fault types: **Top-1 0.7667, Top-3 0.9333, MRR 0.8644, 0 processing failures**.
See [RCAEVAL_V2_BARO_LITE_BENCHMARK.md](./evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md)
and the machine-readable result beside it. The dataset itself is not committed.

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.run /path/to/RCAEval-v2.zip --max-cases 60 --seed 7 \
  --output ../../../docs/aiops/evidence/rcaeval-v2-baro-lite-results.json \
  --report ../../../docs/aiops/evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md
```

## Verification

```bash
cd techx-corp-platform/src/aiops
python -m pytest -q
python -m compileall app
python -m app.observability_smoke

cd ../..
docker compose --env-file .env config --quiet
helm lint ../techx-corp-chart -f ../deploy/values-app-stamp.yaml
```

The deployed service uses private in-cluster endpoints directly: Prometheus
`/api/v1/query[_range]`, OpenSearch `/_search`, and Jaeger
`/jaeger/ui/api/{services,traces}`. Operator evidence may use the documented
Kubernetes service proxy or a reviewed port-forward, but those are not runtime
dependencies of the detector pod. An unavailable secondary source is recorded
as `unavailable`; it is never interpreted as a healthy empty result.
