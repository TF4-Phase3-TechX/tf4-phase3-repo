# Mandate 06 runtime evidence checklist

Only GitHub/PR URLs and sanitized committed artifacts belong in Jira. Do not paste `E:\...` paths, credentials, raw prompts, reviews, responses, PII or Guardrail traces.

## CDO prerequisites

- [ ] Install/confirm `eks-pod-identity-agent`.
- [ ] Create role `tf4-product-reviews-bedrock` from the least-privilege template after a winner exists.
- [ ] Associate namespace `techx-tf4`, ServiceAccount `product-reviews-bedrock`, and the role.
- [x] Create evaluation Guardrail and pin READY version 3; sanitized metadata committed. CDO must confirm promotion/use for canary.
- [ ] Create the non-production leak-detection marker Secret `product-reviews-bedrock-canary` without placing its value in Git/Jira/logs.
- [ ] Temporarily grant the evaluation identity Haiku, Qwen, Nova US profile/destination resources, and the Guardrail.
- [ ] Replace `SET_BY_CDO` in the GitOps values; never deploy that placeholder to canary.
- [ ] Update the two deployed price variables when the winner changes; remove every unused model/profile resource from the IAM template.

## Bake-off record (Vũ, Hậu, Hòa)

- [ ] Re-snapshot `us-east-1` Standard token and Guardrail prices with date/source.
- [x] Run all 30 cases × 3 repetitions through `eval/run_bakeoff.py`; execution used the updated `default` AWS IAM identity rather than the preferred SSO profile.
- [x] Commit only the metadata-only `bakeoff-report.json`; provider-side logging inspection remains pending.
- [ ] Human-review every deterministic failure and ambiguous grounded case.
- [ ] Record winner and rationale in ADR-006; keep `Proposed` until runtime evidence passes.

## Canary and telemetry record (Tâm, Hòa, CDO)

Record UTC window, Git SHA, image digest, model/profile ID, Guardrail version, deployment owner, baseline window and canary window.

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
- [ ] Thông: IAM/CDO/evidence links.
- [ ] Mentor and required ADR approvers.
