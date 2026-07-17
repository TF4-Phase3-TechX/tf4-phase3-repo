# CDO handoff — Bedrock production readiness and controlled deployment

Status: **production prerequisites ready; final PR review/merge and controlled deployment remain pending**.

This runbook is the execution contract between AIO1 and CDO for Mandate 06. It is intentionally explicit enough for a CDO engineer or an AI assistant to follow without relying on chat history. Jira tracking: [SCRUM-94](https://tf4-phase3.atlassian.net/browse/SCRUM-94). Implementation review: [PR #155](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/155).

## 1. Objective and current state

AIO1 has completed the application implementation, local tests and a real-model bake-off for grounded product-review Q&A.

| Item | Value |
|---|---|
| Production AWS account | `511825856493` |
| Evaluation AWS account | `589077667575` |
| Region | `us-east-1` |
| EKS cluster | `techx-tf4-cluster` |
| Kubernetes namespace | `techx-tf4` |
| Workload | `product-reviews` |
| ServiceAccount | `product-reviews-bedrock` |
| Runtime role | `tf4-product-reviews-bedrock` |
| Selected model/profile | `us.amazon.nova-2-lite-v1:0` |
| Evaluation Guardrail | `e2svpiawj1v5`, version `3`, account `589077667575` |
| Production Guardrail | `wckqh9dms6qa`, version `1`, `READY` |
| Pod Identity association | `a-iuw7np6l5niq1k2zt` |
| Pod Identity Agent | `v1.3.10-eksbuild.3`, `ACTIVE` |
| Terraform apply revision | `355cd4e94bbda78225b1b0fe10ff749e6f95afe7` |
| Previous Helm revision | `45` |
| Previous product-reviews image digest | `sha256:3f14cd7b9cf1395b18bb65e8459fbcae1e58527279a5fcb09674aecca3b98136` |
| Proposed deployment window | `2026-07-15T07:00:00Z`–`2026-07-15T09:00:00Z` |
| Application deadline | 4.5 seconds inside a 5-second request budget |
| Runtime fallback | Static unavailable response; never a silent mock/model switch |

The bake-off ran 30 versioned cases three times against three models, producing 270 sanitized records. Nova 2 Lite was the only model to pass all hard gates. The canonical evidence is the [scorecard](model-selection-scorecard.md) and [machine-readable report](eval/bakeoff-report.json).

The evaluation Guardrail is evidence only. CDO08 provisioned the production Guardrail, runtime role, Pod Identity association and canary Secret in account `511825856493`. IAM Access Analyzer validation was reported as `PASS`. CDO08 subsequently applied Terraform revision `355cd4e94bbda78225b1b0fe10ff749e6f95afe7` and reported Pod Identity Agent version `v1.3.10-eksbuild.3` in `ACTIVE` state. Production prerequisites are therefore ready; deployment still requires PR #155 approval/merge and the controlled-deployment gates in this runbook.

## 2. Meaning of “controlled deployment”

The repository does not implement percentage-based or traffic-split canary routing. For this mandate, controlled deployment means:

1. A scheduled verification window with a named CDO deployment owner, AIO witness and rollback owner.
2. The previous immutable image digest and Helm revision are recorded before any change.
3. Production prerequisites are created before merge.
4. The final production configuration commit is reviewed and CI passes.
5. Deployment is aborted and reverted immediately on any safety, identity, latency or Storefront SLO failure.

Do not describe this as a 10% traffic canary. If true traffic splitting is required, it needs a separate reviewed design and implementation.

## 3. Ownership boundary

### CDO owns

- Production Guardrail creation/versioning in account `511825856493`.
- The Nova-only IAM runtime role and EKS Pod Identity association.
- Provisioning the leak-detection marker Secret outside Git.
- The deployment window, immutable release record and rollback execution.
- Returning non-sensitive production metadata to AIO.

### AIO owns

- Updating PR #155 with the production account, Guardrail ID/version and deployment behavior.
- Re-running CI and requesting review of the final production-config commit.
- Application-path safety tests, metric/log/trace inspection and Storefront SLO comparison.
- Updating evidence and ADR-006 after the runtime gates pass.

CDO must not paste credentials, session tokens or the canary marker into Jira, GitHub, chat, logs or screenshots. AIO must not create or mutate production AWS/EKS resources outside the approved CDO process.

## 4. Stop conditions before starting

Stop and comment on SCRUM-94 instead of proceeding when any of the following is true:

- `aws sts get-caller-identity` does not return account `511825856493`.
- The operator cannot inspect or install the EKS Pod Identity Agent.
- Nova 2 Lite cannot be invoked through the US inference profile in the production account.
- The production Guardrail cannot be published as an immutable numeric version.
- The previous Helm revision or image digest cannot be identified.
- The only available deployment path would deploy `BEDROCK_GUARDRAIL_ID=SET_BY_CDO`.
- A requested step would expose a credential, marker, prompt, review, model response or PII.

## 5. Phase A — account and EKS preflight

All commands in this runbook assume a CDO-approved identity and `us-east-1`.

```bash
aws sts get-caller-identity

aws eks describe-cluster \
  --name techx-tf4-cluster \
  --region us-east-1

aws eks describe-addon \
  --cluster-name techx-tf4-cluster \
  --addon-name eks-pod-identity-agent \
  --region us-east-1
```

Expected account: `511825856493`. The Pod Identity Agent must be active. If it is absent, install it through the team's reviewed EKS change process, then wait for it to become active before continuing.

Capture as sanitized evidence:

- UTC timestamp.
- Caller account and assumed role name; omit session tokens.
- Cluster name/region.
- Pod Identity Agent version/status.

## 6. Phase B — create the production Guardrail

Use the reviewed configuration in [`guardrail/create-guardrail.json`](guardrail/create-guardrail.json). Do not use the evaluation Guardrail ID from account `589…`.

```bash
aws bedrock create-guardrail \
  --region us-east-1 \
  --cli-input-json file://docs/aio1/mandate-06/guardrail/create-guardrail.json
```

Record the returned `guardrailId`. Verify the working draft:

```bash
aws bedrock get-guardrail \
  --region us-east-1 \
  --guardrail-identifier <PRODUCTION_GUARDRAIL_ID> \
  --guardrail-version DRAFT
```

Publish an immutable version:

```bash
aws bedrock create-guardrail-version \
  --region us-east-1 \
  --guardrail-identifier <PRODUCTION_GUARDRAIL_ID> \
  --description "Mandate 06 controlled deployment"
```

Verify the returned numeric version:

```bash
aws bedrock get-guardrail \
  --region us-east-1 \
  --guardrail-identifier <PRODUCTION_GUARDRAIL_ID> \
  --guardrail-version <NUMERIC_VERSION>
```

Required result:

- Guardrail account is `511825856493`.
- Region is `us-east-1`.
- A numeric version exists; production does not use `DRAFT`.
- Status is `READY` before deployment.

Return only the ID, numeric version, ARN and READY status to AIO. The Guardrail trace or raw test content is not Jira evidence.

## 7. Phase C — create the runtime IAM role

Create role `tf4-product-reviews-bedrock` with this EKS Pod Identity trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowEksAuthToAssumeRoleForPodIdentity",
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }
  ]
}
```

Base the permission policy on [`iam/runtime-policy-nova.json`](iam/runtime-policy-nova.json), but do not apply that evaluation policy unchanged. Generate a production copy with:

- Account ID `511825856493` for the inference profile and Guardrail ARNs.
- Production Guardrail ID and numeric version from Phase B.
- `bedrock:InvokeModel` only for the Nova 2 Lite US inference profile and required destination foundation-model resources.
- `bedrock:ApplyGuardrail` only for the production Guardrail.
- An explicit deny for inference calls that omit or change the pinned `bedrock:GuardrailIdentifier`.
- No wildcard allow for model invocation.
- No long-lived access key for the pod.

The expected profile resource begins with:

```text
arn:aws:bedrock:us-east-1:511825856493:inference-profile/us.amazon.nova-2-lite-v1:0
```

The expected Guardrail resource begins with:

```text
arn:aws:bedrock:us-east-1:511825856493:guardrail/<PRODUCTION_GUARDRAIL_ID>
```

Validate the final policy with AWS IAM Access Analyzer before attaching it. Attach it only to `tf4-product-reviews-bedrock`.

## 8. Phase D — create the Pod Identity association

Create the association after the role exists:

```bash
aws eks create-pod-identity-association \
  --cluster-name techx-tf4-cluster \
  --namespace techx-tf4 \
  --service-account product-reviews-bedrock \
  --role-arn arn:aws:iam::511825856493:role/tf4-product-reviews-bedrock \
  --region us-east-1
```

Verify it:

```bash
aws eks list-pod-identity-associations \
  --cluster-name techx-tf4-cluster \
  --namespace techx-tf4 \
  --service-account product-reviews-bedrock \
  --region us-east-1
```

Return the association ID/ARN and role ARN to AIO. EKS Pod Identity does not require adding an IAM role annotation to the Kubernetes ServiceAccount.

## 9. Phase E — provision the leak-detection marker

Create this Secret outside Git:

| Field | Value |
|---|---|
| Namespace | `techx-tf4` |
| Secret name | `product-reviews-bedrock-canary` |
| Key | `marker` |
| Value | Cryptographically random, generated by CDO; never shared with AIO |

An illustrative command is shown below. CDO may use the team's approved secret-management process instead.

```bash
kubectl -n techx-tf4 create secret generic product-reviews-bedrock-canary \
  --from-literal=marker='<PRIVATE_RANDOM_VALUE>'
```

Do not paste the real value into shell transcripts retained as evidence. AIO only needs confirmation that the Secret and key exist. The deployment references the key through `valueFrom`; it must never render the marker into Helm values.

## 10. CDO-to-AIO return contract

CDO comments on [SCRUM-94](https://tf4-phase3.atlassian.net/browse/SCRUM-94) with this completed metadata block:

```text
AWS account: 511825856493
Production Guardrail ID:
Production Guardrail numeric version:
Production Guardrail ARN:
Guardrail status: READY
Runtime role ARN:
IAM policy validation result:
Pod Identity association ID/ARN:
Pod Identity Agent version/status:
Canary Secret/key exists: yes/no
Current Helm revision:
Current product-reviews image digest:
Proposed deployment window in UTC:
CDO deployment owner:
AIO witness:
Rollback owner:
```

Do not include credentials, tokens, the canary value, raw application content or local filesystem paths.

## 11. AIO actions after receiving metadata

CDO waits for AIO to complete all of the following before deployment:

1. Replace evaluation account/Guardrail values in the reviewed runtime policy with the production values.
2. Update [`../../../deploy/values-aio-llm.yaml`](../../../deploy/values-aio-llm.yaml) with the production Guardrail ID/version.
3. Ensure the reviewed GitOps production values carry the complete configuration from `deploy/values-aio-llm.yaml`. The current Argo CD application consumes GitOps `app-values.yaml`, `flagd-values.yaml` and `image-revisions.yaml`; it does not consume this repository's deploy overlay directly.
4. Ensure the merge cannot deploy an old image with new Bedrock configuration as an uncontrolled intermediate state.
5. Re-run CI and obtain review of the final production-config commit.
6. Keep ADR-006 in `Proposed` status.

The current chart default contains `BEDROCK_GUARDRAIL_ID=SET_BY_CDO`. Deploying the default chart without the AIO overlay is a blocking error, not an acceptable fallback.

## 12. Pre-deployment record

Before applying the release, CDO records:

```bash
helm -n techx-tf4 history techx-corp

kubectl -n techx-tf4 get deployment product-reviews \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

kubectl -n techx-tf4 get pods,deploy,svc \
  -l app.kubernetes.io/component=product-reviews -o wide
```

Evidence must include:

- UTC start time.
- Git SHA and immutable new image digest.
- Previous image digest and Helm revision.
- Production model/profile and Guardrail numeric version.
- Baseline Storefront availability, error rate and p95 window.
- CDO deployment owner, AIO witness and rollback owner.

## 13. Deployment contract

Use the team's reviewed GitOps promotion path after the final commit is reviewed and merged. `build-and-push.yaml` builds the changed `product-reviews` image and opens or updates the `promotion/production` PR in `tf4-phase3-gitops-manifests`; it does not deploy with Helm directly.

Before the GitOps promotion PR is merged, CDO08 must add the complete AIO production override to the GitOps production values, either in `environments/production/app-values.yaml` or a dedicated reviewed values file referenced by the `techx-corp` Argo CD Application. The effective values must be equivalent to:

```text
deploy/values-app-stamp.yaml
deploy/values-flagd-sync.yaml
deploy/values-aio-llm.yaml
```

Equivalent Helm shape, for render comparison only:

```bash
helm upgrade --install techx-corp ./techx-corp-chart \
  --namespace techx-tf4 \
  --create-namespace \
  --set default.image.repository=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp \
  --set default.image.tag=<REVIEWED_IMAGE_TAG> \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  -f deploy/values-aio-llm.yaml \
  --wait \
  --timeout 10m
```

This command is not authorization to bypass Argo CD. A direct `helm upgrade` would conflict with the GitOps ownership model and must not be used for this rollout. CDO records the GitOps promotion PR, merged GitOps revision, Argo sync revision and resulting Helm revision.

Stop the promotion when the rendered Deployment contains `BEDROCK_GUARDRAIL_ID=SET_BY_CDO`, omits the canary Secret reference, or does not use ServiceAccount `product-reviews-bedrock`.

## 14. Immediate rollout verification

```bash
kubectl -n techx-tf4 rollout status deployment/product-reviews --timeout=5m

kubectl -n techx-tf4 get deployment product-reviews \
  -o jsonpath='{.spec.template.spec.serviceAccountName}'

aws eks list-pod-identity-associations \
  --cluster-name techx-tf4-cluster \
  --namespace techx-tf4 \
  --service-account product-reviews-bedrock \
  --region us-east-1
```

Required results:

- Deployment is Ready.
- ServiceAccount is `product-reviews-bedrock`.
- The association resolves to role `tf4-product-reviews-bedrock`.
- A normal application request reaches Bedrock without `AccessDenied`.
- The runtime identifies Nova 2 Lite and the production Guardrail numeric version.
- The canary marker does not appear in the answer, logs or traces.

Warm the Nova forced-tool/schema path with a small number of normal internal requests before latency measurement.

## 15. Application-path test matrix

Tests must enter through the deployed Storefront/product-reviews path, not by calling only the evaluation runner.

| Test | Expected result |
|---|---|
| Supported grounded question | Answer cites an existing review ID and exact evidence substring |
| Unsupported question | Exact canonical insufficient-information response |
| Stored review injection | Malicious review quarantined; clean evidence only |
| PII/system-prompt extraction | Redacted or blocked; zero leakage |
| Checkout/action request | Exact canonical blocked response; no action performed |
| Provider timeout/error | Exact canonical unavailable response; no mock/model switch |

For each test record case ID, UTC timestamp, outcome and witness. Do not record raw PII, system marker or unnecessary model content.

## 16. Telemetry and SLO verification

Verify the deployed Prometheus contract:

- `app_llm_prompt_tokens_total`
- `app_llm_completion_tokens_total`
- `app_llm_estimated_cost_usd_USD_total` (deployed OTel/Prometheus series; SDK instrument name is `app_llm_estimated_cost_usd_total`)
- `app_llm_latency_seconds`
- `app_llm_errors_total`
- `app_llm_calls_total`

Also verify outcome/fallback/error class and quarantine metadata used by the service. Logs and traces must contain only model ID, Guardrail version, outcome, latency, token counts and safe error classification. They must not contain question, prompt, review, response, PII or canary content.

Compare Storefront availability, error rate and p95 over documented baseline and verification windows. The model call must remain within the 4.5-second deadline and the application request within the five-second budget.

## 17. Abort conditions

Abort and roll back immediately on any of these conditions:

- Pod Identity is missing/wrong or Bedrock returns `AccessDenied`.
- Model invocation does not contain the expected production Guardrail/version.
- Any prompt, review, response, PII or marker leakage occurs.
- Logs or traces capture message content.
- AI request exceeds five seconds.
- Storefront violates its existing SLO.
- Any Mandate 06 hard gate regresses.
- The deployment silently changes model or routes to a mock.

## 18. Rollback drill

Rollback restores the previous reviewed image and configuration revision through the approved GitHub/Helm process. It does not set `LLM_MODE=mock`, silently select another model or mutate flagd.

1. Record rollback UTC start time and trigger reason.
2. Revert to the previous image/configuration revision.
3. Wait for `product-reviews` rollout readiness.
4. Verify the original product/review page and Storefront path.
5. Confirm error rate and latency recovery.
6. Record UTC end time and recovery duration.
7. Attach sanitized workflow/Helm/dashboard evidence URLs to SCRUM-94.

## 19. Completion gate

CDO deployment work is complete when:

- [ ] Pod Identity Agent is healthy.
- [ ] Production Guardrail numeric version is READY in account `511…`.
- [ ] Nova-only runtime role and Pod Identity association are verified.
- [ ] The canary Secret/key exists outside Git.
- [ ] AIO has updated and re-reviewed the final production configuration.
- [ ] The controlled deployment has immutable release evidence.
- [ ] All application-path safety tests pass.
- [ ] Sanitized telemetry and Storefront SLO evidence pass.
- [ ] Provider-failure and rollback drills pass.
- [ ] SCRUM-94 contains metadata/evidence URLs but no secrets or raw content.

Only after the completion gate and named approvals may AIO change ADR-006 from `Proposed` to `Accepted`.

## 20. Machine-readable handoff contract

An AI assistant may use this block as a task map. Production identifiers below were returned by CDO08; the canary marker value remains secret and must not be added here.

```yaml
mandate: 06
status: waiting_for_final_review_and_merge
production:
  account_id: "511825856493"
  region: us-east-1
  cluster: techx-tf4-cluster
  namespace: techx-tf4
  workload: product-reviews
  service_account: product-reviews-bedrock
  model_profile: us.amazon.nova-2-lite-v1:0
  guardrail_id: wckqh9dms6qa
  guardrail_version: "1"
  guardrail_status: READY
  guardrail_arn: arn:aws:bedrock:us-east-1:511825856493:guardrail/wckqh9dms6qa
  runtime_role_arn: arn:aws:iam::511825856493:role/tf4-product-reviews-bedrock
  iam_access_analyzer_validation: PASS
  pod_identity_association_id: a-iuw7np6l5niq1k2zt
  pod_identity_association_arn: arn:aws:eks:us-east-1:511825856493:podidentityassociation/techx-tf4-cluster/a-iuw7np6l5niq1k2zt
  pod_identity_agent_version: v1.3.10-eksbuild.3
  pod_identity_agent_status: ACTIVE
  terraform_apply_revision: 355cd4e94bbda78225b1b0fe10ff749e6f95afe7
  previous_helm_revision: "45"
  previous_product_reviews_image_digest: sha256:3f14cd7b9cf1395b18bb65e8459fbcae1e58527279a5fcb09674aecca3b98136
  deployment_window_utc: 2026-07-15T07:00:00Z/2026-07-15T09:00:00Z
  deployment_owner: CDO08 Team
  aio_witness: AIO01 Team
  rollback_owner: CDO08 Team
  canary_secret:
    name: product-reviews-bedrock-canary
    key: marker
    value_must_not_be_shared: true
evaluation:
  account_id: "589077667575"
  guardrail_id: e2svpiawj1v5
  guardrail_version: "3"
  production_reuse_allowed: false
no_merge_until:
  - pod_identity_agent_active
  - production_guardrail_ready
  - runtime_role_validated
  - pod_identity_associated
  - canary_secret_exists
  - production_values_updated
  - gitops_production_values_updated
  - deployment_overlay_applied
  - final_commit_reviewed
abort_on:
  - access_denied
  - missing_or_wrong_guardrail
  - sensitive_content_leakage
  - content_bearing_telemetry
  - ai_request_over_5_seconds
  - storefront_slo_regression
  - hard_gate_regression
rollback:
  target: previous_reviewed_image_and_configuration
  mock_fallback_allowed: false
evidence_policy:
  allowed:
    - github_urls
    - workflow_urls
    - sanitized_dashboard_captures
    - resource_ids_and_arns
    - timestamps_and_owners
  forbidden:
    - credentials
    - session_tokens
    - canary_marker_value
    - raw_prompts_reviews_or_responses
    - pii
    - local_filesystem_paths
```
