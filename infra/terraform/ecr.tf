# Owner: Huy Hoàng nhóm CDO_04
# ECR repository only. CI builds and pushes images; Terraform must not build Docker images.

resource "aws_ecr_repository" "techx_corp" {
  name                 = "techx-corp"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
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
      "description": "Giữ tối đa 30 ảnh có tag gần nhất",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 30
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF
}