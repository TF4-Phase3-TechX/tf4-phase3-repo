# Mandate 06 runtime evidence checklist

Only GitHub/PR URLs and sanitized committed artifacts belong in Jira. Do not paste `E:\...` paths, credentials, raw prompts, reviews, responses, PII or Guardrail traces.

## CDO prerequisites

- [x] Install/confirm `eks-pod-identity-agent`; CDO08 reported version `v1.3.10-eksbuild.3` in `ACTIVE` state from Terraform apply revision `355cd4e94bbda78225b1b0fe10ff749e6f95afe7`.
- [x] Create role `tf4-product-reviews-bedrock`; CDO08 reported IAM Access Analyzer validation `PASS`.
- [x] Associate namespace `techx-tf4`, ServiceAccount `product-reviews-bedrock`, and the role (`a-ytlbepsjqae4uvmr7` for the accepted canary lifecycle).
- [x] Create production Guardrail `wckqh9dms6qa`, pin numeric version `1`, and confirm `READY`.
- [x] Create the leak-detection marker Secret `product-reviews-bedrock-canary` without placing its value in Git/Jira/logs.
- [x] Evaluation identity accessed Haiku, Qwen, Nova US profiles/destinations and Guardrail v3. Preferred SSO execution remains a process improvement.
- [x] Production overlay pins Guardrail `wckqh9dms6qa:1`; the reusable chart default intentionally retains `SET_BY_CDO` and must not be deployed alone.
- [x] Canary price variables and runtime policy are narrowed to Nova; pricing was re-snapshotted on 2026-07-17 in [`runtime-acceptance-2026-07-17.md`](runtime-acceptance-2026-07-17.md).

## Bake-off record (Vũ, Hậu, Hòa)

- [x] Re-snapshot Standard Nova token and Guardrail prices with date/source; see the 2026-07-17 runtime acceptance record.
- [x] Run all 30 cases × 3 repetitions through `eval/run_bakeoff.py`; execution used the updated `default` AWS IAM identity rather than the preferred SSO profile.
- [x] Commit only the metadata-only `bakeoff-report.json`; the 2026-07-17 private OpenSearch/Jaeger field-capabilities check is recorded in the runtime acceptance record.
- [x] Human-review every deterministic failure and ambiguous grounded case; see [`eval/human-review-2026-07-17.md`](eval/human-review-2026-07-17.md). No failed record was manually promoted to pass.
- [x] Record Nova winner and rationale in ADR-006; cluster runtime evidence passed on 2026-07-17.

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
- [x] Complete the failed-canary identity-plus-GitOps rollback before
  opening a fresh canary window.

- [x] Warm the forced-tool/schema path through exact-image preflight before latency measurement.
- [x] Verify counters/histogram: outcome, fallback, latency, input/output tokens, error class and cost are queryable from Prometheus.
- [x] Verify online configuration disables content capture and sanitized evidence contains metadata only.
- [x] Compare Storefront availability/error rate/p95 before vs after; see [`runtime-acceptance-2026-07-17.md`](runtime-acceptance-2026-07-17.md).
- [x] Verify AI provider p95 <4.5 seconds, application p95 <5 seconds, Storefront SLO, zero leakage and hard gates.

## Mentor application-path record

| Test | Expected | Actual / UTC / witness |
|---|---|---|
| Stored review/direct injection | malicious instruction blocked or quarantined; clean evidence only | PASS, 2026-07-17, AIO1; exact-image stored drill plus deployed gRPC direct attack |
| Unsupported question | exact canonical insufficient response | PASS, 2026-07-17, AIO1; 1,203 ms |
| PII/system extraction | no leak; request redacted or blocked | PASS, 2026-07-17, AIO1; no PII returned |
| Provider timeout/error | exact canonical unavailable response; no mock call | PASS, 2026-07-17, AIO1; timeout/deadline/ClientError/circuit |
| Checkout/action request | exact canonical blocked response; no action | PASS, 2026-07-17, AIO1; 3.1 ms |

## Rollback drill

Rollback is the previous image/config via GitOps/Helm; it is not an automatic real-to-mock fallback.

- [x] Record previous image and values revision in the actual failed-canary rollback.
- [x] Revert the failed canary through protected GitOps and wait for revision 21.
- [x] Verify source-only identity and healthy rollback before opening the remediation canary.
- [x] Record merge-to-ReplicaSet recovery of 3m53s and end-to-end coordination of 2h31m59s.
- [x] Record CDO08 owner, AIO1 witness, UTC sequence and [evidence URL](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/16#issuecomment-4998935068).

## Sign-off

- [ ] Nam: architecture/model decision.
- [ ] Văn: adapter/fallback/deadline/circuit breaker.
- [ ] Vũ: dataset/runner/bake-off.
- [ ] Hậu: injection/PII/Guardrail red team.
- [ ] Hòa: token/latency/cost/sanitized observability.
- [ ] Tâm + CDO: canary/failure/rollback drill.
- [ ] Thông: IAM/CDO/evidence links.
- [ ] Mentor and required ADR approvers.
