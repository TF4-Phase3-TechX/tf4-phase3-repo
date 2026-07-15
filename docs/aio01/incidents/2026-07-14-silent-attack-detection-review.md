# Silent attack detection review — 2026-07-14

- Team: AIO1
- Review started: 2026-07-14 14:34 ICT (`07:34 UTC`)
- Retrospective window: 2026-07-14 `07:10–07:40 UTC` (`14:10–14:40 ICT`)
- Trigger: mentor notification that a silent attack occurred during the preceding approximately 15 minutes
- Outcome: **No automated attack-detection evidence was observable by AIO1. This does not prove that no attack occurred.**

## Executive result

AIO1 could verify Kubernetes resource health, pod logs and EKS control-plane audit logs, but could not execute Prometheus, OpenSearch or Jaeger API queries. The observability services are private, the AIO role did not have `pods/portforward`, and Kubernetes service-proxy requests timed out.

No Kubernetes event, non-system Kubernetes API action, firing-alert log or Alertmanager notification was found for the review window. The configured automatic alerts cover storefront SLO, Kubernetes pressure, observability availability and load-generator traffic; they do not constitute a security/attack detector.

The correct conclusion is therefore:

```text
attack detection: not evidenced
attack absence: not established
automatic alerting for this attack: not evidenced
observability access/coverage gap: confirmed
```

## Evidence collected

### 1. Access boundary

The refreshed AWS role authenticated successfully and belonged to the Kubernetes `ai-readers` group. Relevant authorization result:

```text
get pods/log                              yes
list events                              yes
create pods/portforward, techx-observability  no
```

Public checks returned:

```text
/             HTTP 200
/grafana/     HTTP 404
/jaeger/ui/   HTTP 404
/loadgen/     HTTP 404
/feature      HTTP 404
```

Private exposure is consistent with Mandate 01. However, no working private query path had been supplied to AIO1 at the time of the drill. Attempts to query Prometheus, OpenSearch and Jaeger through Kubernetes `services/proxy` timed out.

### 2. Kubernetes workload state

At the time of the retrospective check, all listed TF4 application and observability pods were `Running`/`Ready`. No application pod showed a restart attributable to the incident window.

Prometheus later restarted at approximately `08:00 UTC`, outside the assumed attack window. Its startup logs reported WAL/exemplar warnings. A Grafana request at the same time recorded `connection refused` to Prometheus. This later interruption affects retrospective observability but is not evidence that the attack caused the restart.

### 3. Kubernetes events

Query:

```powershell
kubectl get events -A -o json
```

Filtered to event timestamps from `07:10–07:40 UTC`:

```text
NO_EVENTS_IN_WINDOW
```

### 4. EKS audit log

CloudWatch log group:

```text
/aws/eks/techx-tf4-cluster/cluster
```

After filtering by `requestReceivedTimestamp`:

```text
audit requests in window: 727
non-system actions:        0
non-lease mutations:       6
```

The six mutations were system activity only:

- one node status patch;
- five HPA status updates for `frontend`/`checkout`.

No human/SSO principal changed a Kubernetes workload, ConfigMap, Secret, RBAC object or flag configuration through the Kubernetes API in this window.

This evidence covers Kubernetes API activity only. It does not cover an application-layer attacker or direct access through a service API.

### 5. Application logs

Selected application logs were retrieved with:

```powershell
kubectl logs deploy/<service> --all-containers --since-time=2026-07-14T07:10:00Z --timestamps
```

Observed line counts included:

```text
cart             668
payment          252
product-reviews   42
```

No error/unauthorized/forbidden/timeout/5xx match was found in these selected stdout logs. Several services emitted no stdout in the window because application telemetry is exported through the observability pipeline. Therefore, absence from pod stdout is not evidence of absence from OpenSearch.

### 6. OTel collection gap

The OTel collector repeatedly failed to scrape Kafka metrics near the start of the review window:

```text
unable to dial: dial tcp: lookup kafka on 172.20.0.10:53: no such host
Error scraping metrics
ListTopics failed
ListGroups failed
```

The collector runs in `techx-observability`, while Kafka runs in `techx-tf4`; the short hostname `kafka` is therefore not a reliable cross-namespace target. Kafka-related attack/lag evidence may have been unavailable.

### 7. Alert configuration and observed alert output

Prometheus had provisioned rules with a 30-second evaluation interval for:

- storefront p95;
- checkout, browse and cart success rates;
- frontend error rate;
- OOM/restart/node/pod pressure;
- Grafana, Prometheus and Jaeger availability;
- load-generator traffic outside the test window.

The Grafana dashboard queried `ALERTS{alertstate=~"pending|firing"}`. These rules are SLO/platform alerts, not security-specific attack rules.

Observed output:

```text
Grafana log: no pending/firing attack-alert transition found
Alertmanager log: no entries in the queried window
Dashboard screenshot: unavailable to AIO1
Prometheus ALERTS history: unavailable to AIO1
```

The absence of Alertmanager log entries is not sufficient proof that no notification was sent; notification delivery requires separate receiver evidence.

### 8. Flag state

The current `flagd-config` ConfigMap showed all fault-injection flags with `defaultVariant: off`, including LLM, catalog, recommendation, ad, Kafka, cart, payment, load-generator, image, readiness and memory-leak flags.

No Kubernetes audit event changed this ConfigMap during the window. Current state does not prove that no in-memory or application-level flag action occurred through another control path.

## Gaps confirmed by the drill

1. AIO1 had no usable private programmatic query route to Prometheus, OpenSearch or Jaeger.
2. Existing alerts are primarily SLO/platform rules and do not identify a generic security attack.
3. Kafka metrics collection was broken by cross-namespace DNS resolution.
4. Successful Alertmanager delivery was not auditable from the available evidence.
5. Pod stdout coverage is incomplete; application-layer investigation depends on OpenSearch access.
6. The AIOps detector was not deployed and therefore could not automatically correlate or summarize the incident.

## Follow-up actions

| Priority | Action | Owner/task |
|---|---|---|
| P0 | Supply AIO1 a private read-only query path, or namespace-scoped `pods/portforward`, for `techx-observability` | CDO / `TF4AIO-36` |
| P0 | Re-run Prometheus `ALERTS`, OpenSearch log and Jaeger trace queries for the retained incident timestamps | AIO1 / `TF4AIO-36`, `TF4AIO-56` |
| P0 | Fix the Kafka receiver target to the approved cross-namespace service FQDN and verify samples | CDO observability owner |
| P1 | Add explicit security/log anomaly coverage after the attack vector is disclosed | AIOps / `TF4AIO-38` |
| P1 | Make detector/alert output durable and routed to the agreed channel | AIOps / `TF4AIO-40` |
| P1 | Record notification delivery evidence and responder acknowledgement | CDO observability owner |

## Reproduction commands

The commands used were read-only and intentionally exclude credentials and response bodies containing sensitive data:

```powershell
kubectl get pods -A -o wide
kubectl get events -A -o json
kubectl logs deploy/<service> --since-time=2026-07-14T07:10:00Z --timestamps
kubectl auth can-i create pods/portforward -n techx-observability
aws logs filter-log-events --log-group-name /aws/eks/techx-tf4-cluster/cluster <bounded timestamps>
```

## Final statement for the drill

TF4 had automatic SLO/platform alert rules, but AIO1 found no evidence that those rules automatically detected the announced silent attack. Because programmatic metric/log/trace access was unavailable and Kafka metric collection was degraded, the team cannot claim that the attack was absent. This drill is retained as negative evidence and an observability/detection-access gap.
