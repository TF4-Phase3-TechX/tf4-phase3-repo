# PERF-04.2 Evidence: CPU and Memory Metrics Blocker

Capture time: 2026-07-09 13:47 +07:00

## Command: pod resource usage

```bash
kubectl -n techx-tf4 top pods
```

Output:

```text
error: Metrics API not available
```

## Command: node resource usage

```bash
kubectl top nodes
```

Output:

```text
error: Metrics API not available
```

## Metrics API check

Command:

```bash
kubectl get apiservice v1beta1.metrics.k8s.io -o wide
```

Output:

```text
Error from server (NotFound): apiservices.apiregistration.k8s.io "v1beta1.metrics.k8s.io" not found
```

Command:

```bash
kubectl get pods -A | Select-String -Pattern 'metrics-server|metrics'
```

Output:

```text
<no output>
```

Finding:

- CPU and memory runtime usage could not be collected because Metrics API is unavailable.
- `metrics-server` does not appear to be installed in the cluster.
- This blocks PERF-04.2 until metrics-server or another Metrics API provider is installed.

