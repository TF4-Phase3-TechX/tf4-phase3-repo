# Mandate 06 runtime evidence checklist

Only GitHub/PR URLs and sanitized committed artifacts belong in Jira. Do not paste `E:\...` paths, credentials, raw prompts, reviews, responses, PII or Guardrail traces.

## CDO prerequisites

- [x] Install/confirm `eks-pod-identity-agent`; CDO08 reported version `v1.3.10-eksbuild.3` in `ACTIVE` state from Terraform apply revision `355cd4e94bbda78225b1b0fe10ff749e6f95afe7`.
- [x] Create role `tf4-product-reviews-bedrock`; CDO08 reported IAM Access Analyzer validation `PASS`.
- [x] Associate namespace `techx-tf4`, ServiceAccount `product-reviews-bedrock`, and the role (`a-iuw7np6l5niq1k2zt`).
- [x] Create production Guardrail `wckqh9dms6qa`, pin numeric version `1`, and confirm `READY`.
- [x] Create the leak-detection marker Secret `product-reviews-bedrock-canary` without placing its value in Git/Jira/logs.
- [x] Evaluation identity accessed Haiku, Qwen, Nova US profiles/destinations and Guardrail v3. Preferred SSO execution remains a process improvement.
- [x] Production overlay pins Guardrail `wckqh9dms6qa:1`; the reusable chart default intentionally retains `SET_BY_CDO` and must not be deployed alone.
- [x] Canary price variables and runtime policy are narrowed to Nova; re-snapshot pricing before CDO rollout.

## Bake-off record (Vũ, Hậu, Hòa)

- [ ] Re-snapshot `us-east-1` Standard token and Guardrail prices with date/source.
- [x] Run all 30 cases × 3 repetitions through `eval/run_bakeoff.py`; execution used the updated `default` AWS IAM identity rather than the preferred SSO profile.
- [x] Commit only the metadata-only `bakeoff-report.json`; provider-side logging inspection remains pending.
- [ ] Human-review every deterministic failure and ambiguous grounded case.
- [x] Record Nova winner and rationale in ADR-006; keep `Proposed` until cluster runtime evidence passes.

## Canary and telemetry record (Tâm, Hòa, CDO)

Record UTC window, Git SHA, image digest, model/profile ID, Guardrail version, deployment owner, baseline window and canary window.

The failed-canary root cause, sanitized pre-fix metrics and coordinated
promotion/rollback constraints are recorded in
[`INCIDENT-2026-07-16-nova-tool-contract.md`](./INCIDENT-2026-07-16-nova-tool-contract.md).
That record remains pre-fix evidence until PR #248 is promoted and the same
application-path gates pass on the new pod revision.

- [x] Record a metadata-only direct account-589 contract probe for the proposed
  cap and Nova-compatible tool schema: 3/3 synthetic runs returned `tool_use`
  and passed the application validator. This is code-level evidence only.
- [x] Pass CI and required human review on the final PR #248 head.
- [x] Complete the current failed-canary identity-plus-GitOps rollback before
  opening a fresh canary window.

- [ ] Warm the structured schema before latency measurement.
- [ ] Verify counters/histogram: outcome, fallback, latency, input/output tokens, error class, quarantine count.
- [ ] Verify logs/traces contain metadata only and content capture is false.
- [ ] Compare storefront availability/error rate/p95 before vs after; attach dashboard query and sanitized capture.
- [ ] Abort if AI >5 seconds, Storefront violates its existing SLO, any leakage occurs, or a hard gate fails.

## Mentor application-path record

| Test | Expected | Actual / UTC / witness |
|---|---|---|
| Stored review injection | malicious review quarantined; answer uses clean evidence only | Pending |
| Unsupported question | exact canonical insufficient response | Pending |
| PII/system extraction | no leak; request redacted or blocked | Pending |
| Provider timeout/error | exact canonical unavailable response; no mock call | Pending |
| Checkout/action request | exact canonical blocked response; no action | Pending |

## Rollback drill

Rollback is the previous image/config via GitOps/Helm; it is not an automatic real-to-mock fallback.

- [ ] Record previous image digest and values revision.
- [ ] Revert the canary GitOps change and wait for rollout completion.
- [ ] Verify workload readiness and original product/review page.
- [ ] Verify error rate/latency recovery and record recovery time objective.
- [ ] Record drill owner, witness, UTC start/end and evidence URL.

## Sign-off

- [ ] Nam: architecture/model decision.
- [ ] Văn: adapter/fallback/deadline/circuit breaker.
- [ ] Vũ: dataset/runner/bake-off.
- [ ] Hậu: injection/PII/Guardrail red team.
- [ ] Hòa: token/latency/cost/sanitized observability.
- [ ] Tâm + CDO: canary/failure/rollback drill.
- [x] Thông: IAM/CDO/evidence links. (Approved on 2026-07-17 via PR #260 review)
- [ ] Mentor and required ADR approvers.
