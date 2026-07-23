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

resource "aws_ecr_lifecycle_policy" "techx_corp_policy" {
  repository = aws_ecr_repository.techx_corp.name

  policy = <<EOF
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Xóa ảnh không có tag (untagged) sau 7 ngày",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 7
      },
      "action": {
        "type": "expire"
      }
    },
    {
      "rulePriority": 2,
      "description": "Giữ tối đa 50 ảnh có tag gần nhất cho promotion và rollback",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 50
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF
}
