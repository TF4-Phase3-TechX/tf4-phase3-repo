# CDO08 Evidence - AIO1 Mandate 06 Platform Gate

**Date:** 2026-07-17  
**UTC evidence time:** 2026-07-17T01:57:22Z  
**AWS account used:** `511825856493`  
**Region:** `us-east-1`  
**EKS cluster:** `techx-tf4-cluster`  
**Namespace:** `techx-tf4`  
**ServiceAccount:** `product-reviews-bedrock`  
**GitOps PR:** https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/22  
**GitOps PR commit checked:** `ba02374501dab50481827e90320361c29bc47b63`  
**Platform gate result:** `NO-GO`

---

## 1. Summary

CDO08 checked the AIO1 Mandate 06 platform gate for PR #22.

Result:

```text
Association read-back: FAIL
Exact image preflight: PARTIAL
Platform GO: NO-GO
```

Reason:

- Current EKS Pod Identity association for `techx-tf4/product-reviews-bedrock` still points to the source role in account `511825856493`.
- Attempting to update the association directly to the target cross-account role in account `589077667575` failed with `Cross-account pass role is not allowed`.
- ECR digest verification with `aws ecr describe-images` could not be completed because the current AWS role lacks `ecr:DescribeImages` on repository `techx-corp`.
- GitOps PR #22 references the expected product-reviews tag and preflight image digest, but this is not enough to send platform `GO` while Pod Identity cannot be switched to the approved target role.

CDO08 did not run the preflight Job because the identity gate failed first.

---

## 2. Caller identity

Command:

```bash
aws sts get-caller-identity
```

Output:

```json
{
  "UserId": "AROAXOKZSY7WVF3EPHAKY:hai",
  "Account": "511825856493",
  "Arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/hai"
}
```

---

## 3. Kubernetes context

Command:

```bash
kubectl config current-context
```

Output:

```text
arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

---

## 4. ServiceAccount read-back

Command:

```bash
kubectl -n techx-tf4 get serviceaccount product-reviews-bedrock -o yaml
```

Sanitized output:

```yaml
apiVersion: v1
automountServiceAccountToken: true
kind: ServiceAccount
metadata:
  labels:
    app.kubernetes.io/component: product-reviews
    app.kubernetes.io/part-of: techx-corp
    argocd.argoproj.io/instance: techx-corp
  name: product-reviews-bedrock
  namespace: techx-tf4
```

Notes:

- ServiceAccount exists.
- It does not use IRSA annotation directly.
- Identity is managed by EKS Pod Identity association.

---

## 5. Current Pod Identity association

Command:

```bash
aws eks list-pod-identity-associations \
  --cluster-name techx-tf4-cluster \
  --region us-east-1
```

Output:

```json
{
  "associations": [
    {
      "clusterName": "techx-tf4-cluster",
      "namespace": "techx-tf4",
      "serviceAccount": "product-reviews-bedrock",
      "associationArn": "arn:aws:eks:us-east-1:511825856493:podidentityassociation/techx-tf4-cluster/a-ytlbepsjqae4uvmr7",
      "associationId": "a-ytlbepsjqae4uvmr7"
    }
  ]
}
```

Command:

```bash
aws eks describe-pod-identity-association \
  --cluster-name techx-tf4-cluster \
  --association-id a-ytlbepsjqae4uvmr7 \
  --region us-east-1
```

Output:

```json
{
  "association": {
    "clusterName": "techx-tf4-cluster",
    "namespace": "techx-tf4",
    "serviceAccount": "product-reviews-bedrock",
    "roleArn": "arn:aws:iam::511825856493:role/tf4-product-reviews-bedrock",
    "associationArn": "arn:aws:eks:us-east-1:511825856493:podidentityassociation/techx-tf4-cluster/a-ytlbepsjqae4uvmr7",
    "associationId": "a-ytlbepsjqae4uvmr7",
    "disableSessionTags": false
  }
}
```

Result:

```text
Association read-back: FAIL
Expected target account: 589077667575
Observed role account: 511825856493
Observed role: tf4-product-reviews-bedrock
```

---

## 6. Attempted target role update

Target role requested by AIO1 runbook:

```text
arn:aws:iam::589077667575:role/tf4-product-reviews-bedrock-emergency-target
```

Command:

```bash
aws eks update-pod-identity-association \
  --cluster-name techx-tf4-cluster \
  --association-id a-ytlbepsjqae4uvmr7 \
  --role-arn arn:aws:iam::589077667575:role/tf4-product-reviews-bedrock-emergency-target \
  --region us-east-1
```

Output:

```text
An error occurred (AccessDeniedException) when calling the UpdatePodIdentityAssociation operation:
Cross-account pass role is not allowed.
```

Result:

```text
Target Pod Identity update: FAIL
Platform GO: NO-GO
```

Interpretation:

- The current platform path cannot directly associate an EKS Pod Identity association in account `511825856493` to the target IAM role in account `589077667575`.
- This is not a workload/app verification failure; it is a platform identity gate failure.

---

## 7. GitOps PR #22 image reference check

Fetched PR #22 into local GitOps branch:

```bash
git -C /Users/haihoang/Documents/Projects/phase3/tf4-phase3-gitops-manifests \
  fetch origin pull/22/head:aio1-pr-22-mandate06
```

Checked commit:

```text
ba02374501dab50481827e90320361c29bc47b63 chore(gitops): prepare Mandate 06 remediation canary
```

Image revision in `environments/production/image-revisions.yaml`:

```yaml
components:
  product-reviews:
    imageOverride:
      tag: "d1c4632-product-reviews"
```

Preflight job image in `environments/production/runbooks/mandate06/preflight-job.yaml`:

```yaml
image: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8a938d6822a1e689dde1f8df01123635dcbd68bea32fa681ff8e439061aaa92
```

Runbook expected digest:

```text
sha256:f8a938d6822a1e689dde1f8df01123635dcbd68bea32fa681ff8e439061aaa92
```

Result:

```text
GitOps PR image tag reference: PASS
Preflight digest reference: PASS
```

Limitation:

```text
ECR tag-to-digest verification could not be completed by CDO08 with the current AWS role.
```

---

## 8. ECR digest check permission blocker

Command:

```bash
aws ecr describe-images \
  --repository-name techx-corp \
  --image-ids imageTag=d1c4632-product-reviews \
  --region us-east-1
```

Output:

```text
AccessDeniedException:
User arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/hai
is not authorized to perform: ecr:DescribeImages
on resource arn:aws:ecr:us-east-1:511825856493:repository/techx-corp
because no identity-based policy allows the ecr:DescribeImages action
```

Required permission for exact ECR verification:

```text
ecr:DescribeImages
resource: arn:aws:ecr:us-east-1:511825856493:repository/techx-corp
```

---

## 9. Final platform decision

CDO08 cannot send platform `GO` at this time.

```text
Association read-back: FAIL
Exact image preflight: PARTIAL
Platform GO: NO-GO
```

Required before platform `GO`:

1. Resolve Pod Identity target-role design:
   - either provide an approved same-account role in `511825856493` that can assume the target account role; or
   - provide the correct supported EKS Pod Identity mechanism for the approved account `589077667575`; or
   - have the platform/IAM owner execute an approved update path that passes AWS constraints.
2. Grant CDO08 or the deployment owner `ecr:DescribeImages` for repository `techx-corp`, or provide an independently approved ECR digest read-back.
3. Re-run association read-back.
4. Re-run exact image preflight.
5. Only then send:

```text
Association read-back: PASS
Exact image preflight: PASS
Platform GO: GO
```
