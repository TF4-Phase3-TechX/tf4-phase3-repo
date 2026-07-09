# PERF-04.4 Evidence: Jaeger Public Route Check

Capture time: 2026-07-09 13:47 +07:00

Command:

```bash
curl.exe -i -L --max-time 20 'http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/jaeger/ui/'
```

Result:

```text
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
server: envoy
title: Jaeger UI
base href="/jaeger/ui/"
```

Observability pod check:

```text
pod/jaeger-7f8ccdd7c9-6fmbm       1/1     Running   0             4h50m
service/jaeger                    ClusterIP   172.20.88.27     <none>   16686/TCP plus collector/query ports
```

Finding:

- Jaeger UI is reachable through the public ALB route `/jaeger/ui/`.
- Checkout trace and product flow trace screenshots are still pending and should be captured manually into `runtime/jaeger/screenshots/`.

