# GitHub Actions CI/CD

This directory contains the GitHub Actions workflows for TechX TF4 Phase 3.

Repository: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| [`ci.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/ci.yaml) | Pull Request to `main` / `master` | Validation only: YAML, Terraform plan, Helm render, Docker smoke build |
| [`build-and-push.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/build-and-push.yaml) | Push to `main` for app changes / manual dispatch | Build and push app images to ECR, then call deploy workflow |
| [`deploy.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/deploy.yaml) | Reusable workflow, manual dispatch, chart/deploy changes on `main` | Helm deploy observability and app to EKS, then smoke test |
| [`terraform-apply.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/terraform-apply.yaml) | Push to `main` for Terraform changes | Apply bootstrap and infra Terraform sequentially |

## Safety model

Pull Requests are validation-only.

PR workflows must not:

- Push Docker images
- Run `terraform apply`
- Run `helm upgrade`
- Configure kubeconfig or deploy to EKS

Only trusted `main` workflows perform side-effecting actions.

## Required GitHub Secrets

These values are produced by `infra/bootstrap` outputs after the GitHub OIDC Terraform bootstrap is applied.

| Secret | Purpose |
|---|---|
| `AWS_GITHUB_ACTIONS_PLAN_ROLE_ARN` | Role used by PR Terraform plan jobs |
| `AWS_GITHUB_ACTIONS_BUILD_ROLE_ARN` | Role used to build and push images to ECR |
| `AWS_GITHUB_ACTIONS_DEPLOY_ROLE_ARN` | Role used to deploy to EKS with Helm |
| `AWS_GITHUB_ACTIONS_TERRAFORM_APPLY_ROLE_ARN` | Role used by main-only Terraform apply workflow |

## Required GitHub Variables

| Variable | Default | Purpose |
|---|---|---|
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_ACCOUNT_ID` | `511825856493` | AWS account ID |
| `ECR_REPOSITORY` | `techx-corp` | ECR repository name |
| `EKS_CLUSTER_NAME` | `techx-tf4-cluster` | EKS cluster name |
| `APP_NAMESPACE` | `techx-tf4` | App Kubernetes namespace |
| `OBS_NAMESPACE` | `techx-observability` | Observability Kubernetes namespace |

## Bootstrap requirement

Before workflows can assume AWS roles, run Terraform bootstrap once with operator credentials:

```sh
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap apply
terraform -chdir=infra/bootstrap output
```

Then copy the role ARN outputs into GitHub repository secrets.

## Deployment notes

- `build-and-push.yaml` generates image tags from the short Git SHA.
- `build-and-push.yaml` calls `deploy.yaml` after image push succeeds.
- `deploy.yaml` can receive `image_tag` from the build workflow.
- Chart/deploy-only changes reuse the currently deployed image tag when no image tag is provided.
- `deploy/values-flagd-sync.yaml` is intentionally excluded from the first CI pass.
- Argo CD / gitops integration is intentionally out of scope for this implementation.
- Ingress auto-apply is intentionally out of scope until AWS Load Balancer Controller is confirmed.

## Runtime validation checklist

After merge and GitHub secrets/variables are configured:

- Open a PR that changes app or IaC files and confirm `ci.yaml` validates without side effects.
- Merge an app change to `main` and confirm `build-and-push.yaml` pushes ECR images.
- Confirm `deploy-after-build` calls `deploy.yaml` with the generated image tag.
- Confirm chart/deploy-only changes trigger `deploy.yaml` directly and deploy observability before app.
- Confirm Terraform changes trigger `terraform-apply.yaml` and apply bootstrap before infra when both changed.
