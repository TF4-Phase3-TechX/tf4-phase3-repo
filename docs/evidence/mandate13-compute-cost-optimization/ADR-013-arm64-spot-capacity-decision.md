# ADR-013 — ARM64 & Spot Capacity Decision with Mandate 21 Reliability Trade-off

## Status
**ACCEPTED / SIGNED**

## Date
2026-07-28

## Context & Problem Statement
Epic-09 Directive #13 targets significant reduction of EKS compute cost by introducing Spot instances and Graviton/ARM64 worker nodes while maintaining customer SLOs (Checkout $\ge 99\%$, Browse/Cart $\ge 99.5\%$, Storefront p95 $< 1000$ms).

Simultaneously, Mandate 21 requires multi-AZ fault tolerance and disaster recovery guarantees. A key requirement is maintaining an On-Demand Reliability Floor so critical control-plane services (Karpenter controller, CoreDNS, EBS CSI, admission controllers) and persistent storage workloads (OpenSearch) remain unaffected during Spot market interruptions or AZ disruptions.

## Decision
1. **100% ARM64 Migration**: All EKS worker nodes (both On-Demand and Spot) are migrated to ARM64 architecture (`t4g.large`, `c7g.large`, `c7g.xlarge`, `r7g.large`).
2. **Approved On-Demand Reliability Floor**:
   - 2 Managed ARM64 `t4g.large` On-Demand nodes across `us-east-1a` and `us-east-1b` as the core cluster bootstrap & control daemon floor.
   - 1 Protected ARM64 `t4g.large` On-Demand node (`us-east-1b`) dedicated to OpenSearch and observability persistent storage (RWO EBS bound).
3. **Spot Ratio Acceptance**:
   - **Steady State Ratio**: ~40% Spot ratio (2 Spot nodes / 5 total nodes) is retained as the intentional steady-state reliability baseline to guarantee Mandate 21 DR compliance.
   - **High-Load Scale-Out Ratio**: During peak variable load, Karpenter provisions additional Spot nodes, scaling Spot ratio to $\ge 50\%$.

## Consequences
- **Positive**: Zero risk of control-plane or OpenSearch eviction during Spot interruption; full compatibility with Mandate 21 DR requirements; ~36.6% to 49.2% compute node-hour reduction achieved.
- **Negative**: Steady-state Spot ratio is capped at 40% when idle to preserve the mandatory 3 On-Demand node reliability floor.

## Sign-off
- **Cost & Performance Lead**: Approved (CDO-04)
- **Platform & Reliability Lead**: Approved (CDO-08 / Reliability)
