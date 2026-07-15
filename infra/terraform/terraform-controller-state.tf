# Argo CD now owns these controllers. Retain live resources while removing
# the legacy Terraform state records during the next apply.
removed {
  from = helm_release.argocd

  lifecycle {
    destroy = false
  }
}

removed {
  from = helm_release.external_secrets

  lifecycle {
    destroy = false
  }
}
