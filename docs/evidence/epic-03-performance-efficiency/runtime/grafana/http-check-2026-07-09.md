# PERF-04.3 Evidence: Grafana Public Route Check

Capture time: 2026-07-09 13:47 +07:00

Command:

```bash
curl.exe -i -L --max-time 20 'http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/grafana/'
```

Result:

```text
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
server: envoy
title: Grafana
```

Observability pod check:

```text
pod/grafana-5669788d6c-jhfmw      4/4     Running   3 (62m ago)   122m
service/grafana                   ClusterIP   172.20.108.200   <none>   80/TCP
```

Finding:

- Grafana is reachable through the public ALB route `/grafana/`.
- Dashboard screenshots are still pending and should be captured manually into `runtime/grafana/screenshots/`.

