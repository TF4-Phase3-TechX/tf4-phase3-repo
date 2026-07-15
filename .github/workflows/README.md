# GitHub Actions CI/CD

This directory contains the GitHub Actions workflows for TechX TF4 Phase 3.

Repository: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| [`ci.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/ci.yaml) | Pull Request to `main` / `master` | Validation only: YAML, Terraform plan, Helm render, Docker smoke build |
| [`build-and-push.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/build-and-push.yaml) | Push to `main` for app changes / manual dispatch | Build affected images, verify ECR digests, then open or update a reviewed GitOps promotion PR |
| [`deploy.yaml`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/.github/workflows/deploy.yaml) | Manual dispatch only | Emergency Helm fallback during the rollback window; do not use while Argo manages the release |
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
| `AWS_GITHUB_ACTIONS_DEPLOY_ROLE_ARN` | Emergency-only role used by manual Helm fallback during the rollback window |
| `AWS_GITHUB_ACTIONS_TERRAFORM_APPLY_ROLE_ARN` | Role used by main-only Terraform apply workflow |
| `GITOPS_PROMOTION_APP_ID` | GitHub App ID used to open GitOps promotion PRs |
| `GITOPS_PROMOTION_APP_PRIVATE_KEY` | GitHub App private key used to open GitOps promotion PRs |

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

- `build-and-push.yaml` generates image tags from the short Git SHA and updates only changed service image overrides.
- A push builds images only for services changed under `techx-corp-platform/src/<service>/`.
- A push changing `techx-corp-chart/**` opens or updates the GitOps promotion PR with the full immutable source SHA for both chart Applications; it does not build images.
- A combined service and chart push updates the selected image overrides and both chart source SHA pins in one GitOps promotion PR. Other workflow or deploy-script changes create neither images nor a promotion PR.
- Manual dispatch requires an explicit comma-separated service list and never advances a chart source pin.
- Each run rebuilds `promotion/production` from the current GitOps `main`, applies only that run's revisions, and force-updates the single PR branch with lease protection; a platform owner reviews and merges the GitOps PR.
- Argo CD deploys the merged GitOps revision; build CI never invokes direct Helm deployment.
- `deploy.yaml` is an emergency-only manual fallback and must not run while Argo manages the same release.
- Ingress auto-apply is intentionally out of scope until AWS Load Balancer Controller is confirmed.

## Runtime validation checklist

After merge and GitHub secrets/variables are configured:

- Open a PR that changes app or IaC files and confirm `ci.yaml` validates without side effects.
- Merge a payment-only app change to `main`; confirm only the payment image is pushed and only its GitOps image override changes.
- Confirm a platform/deploy-script change creates no ECR image and no GitOps promotion PR.
- Confirm manual dispatch rejects an empty or unknown service list.
- Confirm the GitHub App opens or updates `promotion/production`, then merge it after review.
- Confirm Argo rolls out only the promoted workload and a GitOps revert restores the preceding tag.
- Confirm Terraform changes trigger `terraform-apply.yaml`.
