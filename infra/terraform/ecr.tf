# Khai báo ECR Repository
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

# Cấu hình Lifecycle Policy tự động dọn dẹp ảnh rác
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

# Tự động sinh file .env.override từ kết quả ECR URL
resource "local_file" "env_override" {
  filename = "${path.module}/../../techx-corp-platform/.env.override"
  content  = <<EOF
IMAGE_NAME=${aws_ecr_repository.techx_corp.repository_url}
IMAGE_VERSION=1.0
DEMO_VERSION=1.0
EOF
}

# Tự động đăng nhập ECR và trigger script build tuần tự
resource "null_resource" "build_and_push_images" {
  depends_on = [
    aws_ecr_repository.techx_corp,
    local_file.env_override
  ]

  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<EOF
aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.techx_corp.repository_url}
bash ./deploy/build-push-images.sh
EOF

    interpreter = ["PowerShell", "-Command"]
  }
}

# Xuất URL ECR Repository ra màn hình sau khi hoàn thành
output "ecr_repository_url" {
  description = "URL của AWS ECR Repository"
  value       = aws_ecr_repository.techx_corp.repository_url
}
