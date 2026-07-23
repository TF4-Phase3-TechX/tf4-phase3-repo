# D5-PERF-03 resource remediation overlays

Place the reviewed, cumulative Helm overlay for each wave here:

1. `01-low-risk-stateless.yaml`
2. `02-revenue-critical-stateless.yaml`
3. `03-stateful-messaging.yaml`
4. `04-observability.yaml`
5. `05-remaining-exceptions.yaml`

Each enabled application component must contain `requests.cpu`,
`requests.memory`, `limits.cpu`, and `limits.memory`. Values must come from
D5-02 runtime evidence; do not copy a small default across services.

The five overlays contain the reviewed measured resource matrix and are applied
cumulatively by the controlled rollout harness.
The rollout script refuses a missing overlay.

