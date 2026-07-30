# Mandate 22 GitOps production drill gate

The prior direct-Deployment drill procedure is superseded. Do not reuse its
ReplicaSet pin, live patch RBAC, Argo mutation window or self-heal exception.

## Go gates

- App implementation PR is merged and the exact AIOps image/chart SHA is pinned.
- GitOps bootstrap PR is merged while mode remains `gitops/dry-run` and
  autonomous remediation remains false.
- CDO evidence proves the approved GitOps App permissions, required rulesets,
  ESO Secret readiness, CONNECT proxy allowlist and NetworkPolicy.
- Argo `techx-corp` has `automated.selfHeal=true`; there is no pod-template
  ignore rule.
- No non-terminal saga V1 exists.
- Kind/Argo rounds pass:
  - success;
  - forced-wrong plus compensation;
  - restart/API-timeout/merge-race.
- Activation PR changes only the reviewed image/chart identity and:
  `gitops/live`, autonomous true, allowlist `product-reviews`.
- Named CDO and on-call/SRE owners accept the drill window and escalation.

Any missing gate is NO-GO. There is no direct Kubernetes fallback.

## Success drill

1. Merge a bounded fault PR containing the three
   `MANDATE22_REVIEW_DELAY_*` entries with TTL and request cap.
2. Generate owned traffic only through `/api/product-reviews/<id>`. Do not call
   Bedrock/AI for this drill.
3. Capture:
   - incident and protected policy SHA;
   - remediation branch/PR;
   - all three required checks;
   - head and merge SHA;
   - Argo sync/rollout identity;
   - correlation annotation and managed env absence;
   - exact review-RPC volume/latency/error samples;
   - three healthy polls and terminal `resolved` saga.

## Forced-wrong drill

Use only the separately reviewed, signed and expiring forced-wrong profile. The
candidate may change the correlation annotation while deliberately retaining
the fault.

Pass requires:

- verification fails;
- exactly one compensation PR opens;
- compensation restores the pre-action Git and runtime identity;
- the original incident remains escalated and mutation-quarantined;
- no `resolved` claim is made.

Cleanup is a reviewed PR that removes the fault and forced-wrong profile.
Operator clear of the durable quarantine is a separate authenticated audit
event.

## Stop conditions

Suspend the GitHub App, then merge the prepared kill-switch PR for any:

- duplicate/unauthorized PR;
- ruleset or required-check bypass;
- wrong runtime identity;
- low telemetry volume;
- unhealthy verification;
- Lease loss;
- compensation failure;
- change outside the exact managed surface.

After a successful cleanup, keep the correct product-reviews GitOps policy live
as Nam requested. Drill completion alone is not a reason to restore dry-run.

## Claim boundary

Technical runtime success without named CDO and on-call/SRE signatures is
evidence level 5 at most. TF4AIO-83 and the mandate remain unaccepted until the
full evidence chains in ADR-022 and final signatures exist.
