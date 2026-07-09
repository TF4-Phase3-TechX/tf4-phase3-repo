# PERF-04 Evidence: Warning Events

Capture time: 2026-07-09 13:47 +07:00

Command:

```bash
kubectl get events -A --field-selector type=Warning
```

Output:

```text
NAMESPACE             LAST SEEN   TYPE      REASON      OBJECT                            MESSAGE
techx-observability   60m         Warning   Unhealthy   pod/grafana-5669788d6c-jhfmw      Readiness probe failed: Get "http://10.0.10.185:3000/api/health": dial tcp 10.0.10.185:3000: connect: connection refused
techx-tf4             15s         Warning   BackOff     pod/accounting-6696f5bdb8-7wvkg   Back-off restarting failed container accounting in pod accounting-6696f5bdb8-7wvkg_techx-tf4(72854557-82eb-4a9e-a9de-bf5ebec6548e)
```

Finding:

- `accounting` is currently the main runtime warning to investigate.
- Grafana had a previous readiness warning but is currently running.

