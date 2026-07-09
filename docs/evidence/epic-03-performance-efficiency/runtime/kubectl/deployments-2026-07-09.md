# PERF-04 Evidence: Deployment Readiness

Capture time: 2026-07-09 13:47 +07:00

Command:

```bash
kubectl get deploy -n techx-tf4
```

Output:

```text
NAME              READY   UP-TO-DATE   AVAILABLE   AGE
accounting        1/1     1            1           36h
ad                1/1     1            1           36h
cart              1/1     1            1           36h
checkout          1/1     1            1           36h
currency          1/1     1            1           36h
email             1/1     1            1           36h
flagd             1/1     1            1           36h
fraud-detection   1/1     1            1           36h
frontend          1/1     1            1           36h
frontend-proxy    1/1     1            1           36h
image-provider    1/1     1            1           36h
kafka             1/1     1            1           36h
llm               1/1     1            1           36h
load-generator    1/1     1            1           36h
payment           1/1     1            1           36h
postgresql        1/1     1            1           36h
product-catalog   1/1     1            1           36h
product-reviews   1/1     1            1           36h
quote             1/1     1            1           36h
recommendation    1/1     1            1           36h
shipping          1/1     1            1           36h
valkey-cart       1/1     1            1           36h
```

Finding:

- All application deployments are currently available with `READY 1/1`.

