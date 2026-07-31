# ADR-022: GitOps-native auto-remediation for product-reviews

- Date superseded: 2026-07-30
- Status: **Proposed implementation; CDO bootstrap, production runtime evidence,
  named on-call/SRE acceptance and final signatures remain pending**
- Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)
- Policy: `m22-gitops-v1`

This revision supersedes every earlier ADR-022 decision that authorized direct
Deployment template patching, retained-ReplicaSet selection, Argo mutation
windows, or `/spec/template` `ignoreDifferences`.

## Decision

V1 handles exactly `product-reviews/service_latency_spike`. The bounded fault
and remediation surface is:

- `MANDATE22_REVIEW_DELAY_MS`
- `MANDATE22_REVIEW_DELAY_TTL_SECONDS`
- `MANDATE22_REVIEW_DELAY_MAX_REQUESTS`
- pod correlation annotation `aiops.techx.io/remediation-id`

The detector may create one remediation branch and PR:

`aiops/remediation/<incident-id>`

The PR restores the three managed environment entries from the CDO-owned
known-good Git SHA and adds the correlation annotation. It changes only
`environments/production/app-values.yaml`. Required checks must prove the
semantic values delta and that Helm rendering changes only the pod template of
`Deployment/product-reviews`.

After all required checks succeed, the GitHub App enables auto-merge. Repository
rules prohibit direct push and prohibit the bot from bypassing required checks.
Argo CD, with `selfHeal=true`, reconciles the merged commit to the cluster.
AIOps reads runtime status and verifies the exact product-review RPC telemetry;
it never writes a Deployment, ReplicaSet, Argo Application, Rollout or flagd.
The only Kubernetes write is a target-scoped coordination Lease.

### Time-boxed demo exception

The 2026-07-31 demonstration may use two distinct fine-grained user tokens
because the delivery owner cannot modify the organization-owned GitHub App
before the demo window. The creator token may open only the bounded remediation
PR. The reviewer token may approve and merge only after the same three protected
checks succeed. Both credentials are repository-scoped and expire after the
demo.

This is a `dual-token scripted demo`, not the production identity model. It
cannot satisfy the CDO-owned GitHub App acceptance condition and must never be
reported as autonomous level 6. Production remains the GitHub App flow above.

Failed verification creates at most one compensation branch and PR:

`aiops/compensation/<incident-id>`

Compensation restores the exact pre-action structured target hash. Successful
compensation does not resolve the original incident: mutation remains
quarantined and escalation remains open until an audited operator action.

## Durable transaction

Saga schema V2 records:

- policy, base and known-good Git SHAs;
- before/after structured hashes;
- deterministic branches, PR identity, check conclusions, head and merge SHA;
- expected and observed runtime identity;
- remediation and compensation transactions;
- verification samples, quarantine and escalation.

Phases:

`PREFLIGHT -> PR_OPEN -> CHECKS_PENDING -> MERGE_QUEUED -> MERGED -> RUNTIME_PENDING -> VERIFYING -> COMPENSATING -> TERMINAL`

After an ambiguous GitHub write response, recovery first rediscovers the
deterministic branch and PR. It never creates a second remediation PR and never
creates more than one compensation PR. Existing schema V1 records remain
readable, but any non-terminal V1 record blocks `gitops/live` activation.

## GitHub and network boundary

CDO reuses the existing `gitops-promotion-bot-tf4` GitHub App. Its AIOps
installation token remains scoped only to
`TF4-Phase3-TechX/tf4-phase3-gitops-manifests`:

- Metadata: read
- Contents: read/write
- Pull requests: read/write
- Checks: read
- no Administration, Actions, Secrets or other repository access

The private key is stored in AWS Secrets Manager account `511825856493`,
synced through External Secrets Operator and mounted read-only. The Bedrock
account is not part of this path. AIOps reaches `api.github.com:443` only
through a CDO-owned CONNECT proxy whose application policy allowlists that
hostname; NetworkPolicy gives AIOps no direct public egress.

Two repository rulesets are required before activation:

1. `validate`, `check-pinned-dependencies` and
   `aiops-remediation-policy` are required with no bot bypass.
2. The App may bypass only the human PR-review requirement.

If App permissions, rules or required checks do not match this contract, the
controller stops before merge and escalates. There is no Kubernetes fallback.

## Trade-offs

GitHub checks and Argo reconciliation increase remediation latency and introduce
two external control-plane dependencies. In exchange, desired state remains
Git-authoritative, self-heal remains continuously enabled, every action is
reviewable by policy, and recovery cannot be silently overwritten by Argo.

V1 deliberately excludes multi-service remediation, resource/image rollback,
Argo Rollouts migration and free-form Kubernetes mutation.

## Activation and stop conditions

Activation requires a separate reviewed PR that sets:

- `REMEDIATION_MODE=gitops/live`
- `AIOPS_AUTONOMOUS_REMEDIATION_ENABLED=true`
- allowlist exactly `product-reviews`

Before production, Kind/Argo sandbox evidence must cover successful remediation,
forced-wrong compensation, and restart/API-timeout/merge-race recovery.

Suspend the GitHub App and merge the prepared kill-switch PR when any of these
occur:

- unauthorized or duplicate PR;
- required-check/ruleset bypass;
- wrong runtime identity;
- compensation failure;
- Lease ownership loss;
- telemetry below the verification floor;
- a change outside the policy-managed surface.

After technical success, keep the correct product-reviews policy live as Nam
requested. Do not automatically restore dry-run merely because the drill ends.

## Ownership and signature gate

| Owner | Accountability |
|---|---|
| Nam | implementation/delivery DRI, production operator, evidence coordinator |
| Hòa | saga V2, idempotent recovery and compensation |
| Hậu | bounded traffic, drill timeline and telemetry capture |
| Thành Tâm | Jira accountable/defender for TF4AIO-83 |
| CDO | GitHub App, rulesets, ESO secret, proxy/egress and GitOps approval |
| Named on-call/SRE | escalation acceptance and final ADR/Jira sign-off |

Signature record:

| Name | Role | Decision | Date |
|---|---|---|---|
| Đinh Danh Nam | Implementation DRI | Pending review of this superseding decision | — |
| _Name required_ | CDO owner | Pending bootstrap/activation approval | — |
| _Name required_ | On-call/SRE | Pending escalation and live-drill acceptance | — |

TF4AIO-83 closes only when evidence links:

`incident -> policy -> PR/checks -> merge SHA -> Argo rollout -> real telemetry -> terminal saga`

and:

`wrong action -> verify fail -> compensation PR -> original state restored -> escalation/block`

Implementation and offline tests are evidence level 3 at most. A deployed
technical path without the named signatures is runtime level 5 at most, never
mandate accepted/level 6.
