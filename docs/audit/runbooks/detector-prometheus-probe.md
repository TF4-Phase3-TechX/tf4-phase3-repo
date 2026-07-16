# Detector Prometheus Probe Runbook

## Owner
- AIOps on-call

## Purpose
Validate the Prometheus probe emitted by the detector and route failures to the correct escalation path.

## Trigger
- Detector logs emit `incident_type=prometheus_probe_empty` or `incident_type=prometheus_probe_error`.
- Detector summary indicates no `up==1` samples or probe failure.

## Prerequisites
- Access to the `techx-observability` namespace.
- Access to the `techx-tf4` namespace for detector logs.
- The detector pod is running.

## Procedure
1. Check the latest detector event.
   - `kubectl -n techx-tf4 logs deploy/detector --tail=20`
2. Confirm the detector is probing the correct Prometheus endpoint.
   - `http://prometheus.techx-observability.svc.cluster.local:9090/api/v1/query?query=up%20%3D%3D%201`
3. If the event is `prometheus_probe_empty`, inspect whether Prometheus has any `up==1` targets.
   - `kubectl -n techx-observability get pods -l app=prometheus`
   - `kubectl -n techx-observability logs deploy/prometheus --tail=50`
4. If the event is `prometheus_probe_error`, validate service reachability and DNS.
   - Check service existence and endpoints in `techx-observability`.
5. Create an incident ticket and route to the owning team.
   - Use the detector payload `owner_response_path=open-runbook-then-create-incident-ticket`.

## Evidence to capture
- Detector log line.
- Prometheus service/pod status.
- Any ticket or follow-up action taken.

## Rollback / stop conditions
- Stop after capturing evidence and assigning the ticket.
- No automatic remediation is performed by the detector.
