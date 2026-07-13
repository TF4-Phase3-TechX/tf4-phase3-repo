# Task-4 Cost Efficiency Summary

## 1. Full-run context

- Full-run traffic: 200 concurrent users with Task-4 load shape.
- Expected runtime: 16m20s (1m ramp-up, 15m steady-state, 20s ramp-down).
- Evidence artifacts:
  - `task4-full-stats.csv`
  - `task4-full-report.html`
  - `task4-full-T0.txt`
  - `task4-full-T1.txt`
  - monitor log: `load-test-monitor-*.log`

## 2. Baseline capacity and cost

| Metric | Baseline | Notes |
|---|---|---|
| Worker nodes | 2 nodes | EKS worker group currently desired=2, min=2, max=4 |
| Instance type | `t3.large` | Baseline current compute cost driver |
| Node cost estimate | `$56.83/week` | From existing `COST-05` estimate |
| NAT Gateway | 1 | Fixed cost driver |
| ALB | 1 | Fixed cost driver |

## 3. Full-load estimate

| Metric | Full-run value | Notes |
|---|---|---|
| Concurrent users | 200 | Task-4 target |
| Duration | 16m20s | Full run window |
| CSV total requests | `7800` | Placeholder from `task4-full-stats.csv` |
| Successful checkout rate | `99.58%` | Placeholder evidence value |
| Storefront p95 | `820ms` | Placeholder evidence value |

## 4. Cost per request/order comparison

| Metric | Baseline cost | Full-run cost | Notes |
|---|---|---|---|
| Cost per request | `$56.83/week` / `~7800 requests` | `$0.0073/request` | Weekly baseline spread over full-run request volume |
| Cost per checkout order | `$56.83/week` / `~200 checkout orders` | `$0.284/order` | Approximate cost using checkout traffic share |

## 5. Findings

- The full-run evidence package must include the real `task4-full-stats.csv` and `task4-full-report.html` generated from Locust headless execution.
- The cost efficiency summary must be updated with actual request counts and final AWS node cost data from Cost Explorer.
- Current baseline vs full-run comparison is intended for Week 1 evidence; any later optimization should preserve `cost/request` and `cost/order` stability.
