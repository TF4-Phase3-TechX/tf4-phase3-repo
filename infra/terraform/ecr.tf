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
  # Mọi thư mục techx-corp-platform/src/<service>/ có Dockerfile đều được build/push
  # vào chung 1 repo ECR "techx-corp", tag dạng "<commit>-<service>". Trước đây rule 2
  # đếm CHUNG toàn repo ("keep 50 most recent, any tag") - ở tốc độ push hiện tại
  # (~74 ảnh/ngày, xem evidence trong PR) cửa sổ 50 ảnh đó bị lấp đầy trong CHƯA ĐẾN 1
  # NGÀY, khiến các service ít build lại (accounting/ad/cart/fraud-detection) bị mất
  # cả ảnh ĐANG CHẠY THẬT dù không ai đụng tới. Danh sách dưới đây tách rule đếm RIÊNG
  # cho từng service (theo hậu tố tag) để mỗi service luôn giữ N bản build gần nhất
  # của chính nó, không bị ảnh hưởng bởi tần suất build của service khác.
  #
  # KHÔNG có rule "any"/global nào ở đây theo chủ ý: ECR không hỗ trợ "loại trừ" khi
  # đếm, nên 1 rule "any" đếm chung sẽ xoá theo tổng bất kể rule per-service nói gì,
  # tái tạo lại đúng lỗi ban đầu. Vì vậy chỉ dùng rule per-service; tổng ảnh tối đa =
  # 22 service x 2 = 44, vẫn dưới ngưỡng 50 cũ. Đánh đổi: service mới thêm sau này
  # (chưa có trong danh sách) sẽ KHÔNG được rule nào bảo vệ tới khi được thêm vào đây.
  ecr_techx_corp_services = [
    "accounting", "ad", "aiops", "cart", "checkout", "currency", "email",
    "flagd-ui", "fraud-detection", "frontend-proxy", "frontend", "image-provider",
    "kafka", "llm", "load-generator", "opensearch", "payment", "product-catalog",
    "product-reviews", "quote", "recommendation", "shipping",
  ]

  # 2, không phải 1: ngay sau khi 1 build mới push xong (tag mới nhất) nhưng PR
  # promote chưa merge, ảnh ĐANG chạy thật vẫn là ảnh mới-nhì (không phải mới nhất)
  # của service đó. Giữ đúng 1 sẽ xoá luôn ảnh đang chạy ngay khi build kế tiếp xong,
  # tái tạo lại chính sự cố này ở quy mô nhỏ hơn nhưng lặp lại liên tục.
  ecr_techx_corp_keep_per_service = 2

  ecr_techx_corp_per_service_rules = [
    for idx, svc in local.ecr_techx_corp_services : {
      rulePriority = idx + 2 # priority 1 = untagged rule bên dưới
      description  = "Giữ ${local.ecr_techx_corp_keep_per_service} ảnh gần nhất riêng cho service '${svc}' (không bị service khác lấn)"
      selection = {
        tagStatus      = "tagged"
        tagPatternList = ["*-${svc}"]
        countType      = "imageCountMoreThan"
        countNumber    = local.ecr_techx_corp_keep_per_service
      }
      action = { type = "expire" }
    }
  ]

  ecr_techx_corp_policy = {
    rules = concat(
      [
        {
          rulePriority = 1
          description  = "Xóa ảnh không có tag (untagged) sau 7 ngày"
          selection = {
            tagStatus   = "untagged"
            countType   = "sinceImagePushed"
            countUnit   = "days"
            countNumber = 7
          }
          action = { type = "expire" }
        }
      ],
      local.ecr_techx_corp_per_service_rules,
    )
  }
}

resource "aws_ecr_lifecycle_policy" "techx_corp_policy" {
  repository = aws_ecr_repository.techx_corp.name
  policy     = jsonencode(local.ecr_techx_corp_policy)
}
