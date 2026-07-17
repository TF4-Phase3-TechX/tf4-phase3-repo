# Deployment and Operations Guide — TF4AIO-45

This guide addresses crucial operational dependencies and risk mitigation strategies identified during the review of the observability and LLM timeout detector implementation (PR #258).

---

## 1. Karpenter Security Group Deployment Order Dependency

### Context
In `deploy/karpenter/ec2nodeclass.yaml`, the Security Group selection tags were updated to migrate from the broad `karpenter.sh/discovery` tag to the more specific, secure, and isolated `karpenter.sh/node-security-group` tag:
```yaml
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/node-security-group: techx-tf4-cluster
```

### Risk & Impact
Infrastructure (Terraform) and Kubernetes configuration (ArgoCD/GitOps) deployment pipelines run asynchronously.
If ArgoCD synchronizes the updated `ec2nodeclass.yaml` **before** Terraform applies the new `karpenter.sh/node-security-group` tag to the AWS security groups, Karpenter will fail to identify the required Security Group. This blocks auto-scaling, preventing the provisioning of new EC2 nodes.

### Mitigation & Recommendations
- **Enforce strict deployment sequencing**: Ensure that `terraform apply` has successfully executed on AWS (verifying that the security groups are tagged with `karpenter.sh/node-security-group: techx-tf4-cluster`) before allowing ArgoCD to synchronize the Karpenter configuration changes.
- **Manual Verification**: Run the following AWS CLI command to verify tags before syncing ArgoCD:
  ```bash
  aws ec2 describe-security-groups --filters "Name=tag:karpenter.sh/node-security-group,Values=techx-tf4-cluster"
  ```

---

## 2. Bedrock Canary Secret Presence Across Non-Production Namespaces

### Context
The production Helm values in `deploy/values-aio-llm.yaml` reference the environment variable `BEDROCK_SYSTEM_CANARY` from a Kubernetes Secret named `product-reviews-bedrock-canary` via `valueFrom.secretKeyRef`:
```yaml
      - name: BEDROCK_SYSTEM_CANARY
        valueFrom:
          secretKeyRef:
            name: product-reviews-bedrock-canary
            key: marker
```

### Risk & Impact
Currently, this Secret is only provisioned on the Production namespace. If the same `values-aio-llm.yaml` or a unified Helm value structure is applied in testing, staging, or development environments without this Secret being present, Kubernetes will fail to inject the environment variable, causing the `product-reviews` pods to go into a `CreateContainerConfigError` state and crash.

### Mitigation & Recommendations
To maintain environment parity and prevent deployment failures on Dev/Staging, a placeholder (dummy/fake) Secret must be created in every target namespace.

#### Manifest Template for Dev/Staging
Deploy the following manifest to any non-production namespaces (e.g., `dev`, `staging`) where the LLM integration is deployed:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: product-reviews-bedrock-canary
  namespace: dev # Replace with staging or other target namespaces
type: Opaque
stringData:
  marker: "dummy-canary-key-for-testing"
```

Apply this manifest using:
```bash
kubectl apply -f dummy-canary-secret.yaml -n dev
kubectl apply -f dummy-canary-secret.yaml -n staging
```
