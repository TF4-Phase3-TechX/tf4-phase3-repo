# Owner: Huy Hoàng nhóm CDO_04
# ECR repository only. CI builds and pushes images; Terraform must not build Docker images.

resource "aws_ecr_repository" "techx_corp" {
  name                 = "techx-corp"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  lifecycle {
    # Runtime uses IMMUTABLE_WITH_EXCLUSION for sha256-* artifact tags used by
    # signing/attestation workflows. The current AWS provider schema in this
    # repo cannot model that exclusion yet, so do not revert it to IMMUTABLE.
    ignore_changes = [image_tag_mutability]
  }
}

locals {
  ecr_src_dir  = "${path.module}/../../techx-corp-platform/src"
  ecr_services = distinct([for f in fileset(local.ecr_src_dir, "**/Dockerfile") : split("/", f)[0]])

  ecr_lifecycle_rules = concat(
    [{
      rulePriority = 1
      description  = "Xóa ảnh không có tag (untagged) sau 7 ngày"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 7
      }
      action = { type = "expire" }
    }],
    [for i, svc in local.ecr_services : {
      rulePriority = i + 2
      description  = "Giữ tối đa 2 image mới nhất cho service ${svc}"
      selection = {
        tagStatus      = "tagged"
        tagPatternList = ["*-${svc}"]
        countType      = "imageCountMoreThan"
        countNumber    = 2
      }
      action = { type = "expire" }
    }]
  )
}

resource "aws_ecr_lifecycle_policy" "techx_corp_policy" {
  repository = aws_ecr_repository.techx_corp.name
  policy     = jsonencode({ rules = local.ecr_lifecycle_rules })
}
