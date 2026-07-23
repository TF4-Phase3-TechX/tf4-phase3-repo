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
  # Tự sinh danh sách service từ filesystem thay vì hardcode, để thêm service mới
  # (thư mục có Dockerfile dưới techx-corp-platform/src) không cần sửa file này.
  # Dùng "**/Dockerfile" (không phải "*/Dockerfile") vì cart có Dockerfile ở
  # src/cart/src/Dockerfile. Có thể lẫn vài dir không thực sự được CI build/push
  # (vd flagd-ui, opensearch) — vô hại vì rule không khớp ảnh nào thì không làm gì.
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
      description  = "Giữ tối đa 2 ảnh mới nhất cho service ${svc}"
      selection = {
        tagStatus      = "tagged"
        tagPatternList = ["*-${svc}"]
        countType      = "imageCountMoreThan"
        countNumber    = 2
      }
      action = { type = "expire" }
    }]
  )

  # Cosign sinh 2 tag phụ cho mỗi image đã ký thành công: "sha256-<digest>.sig"
  # (chữ ký, ~0.5 KB) và "sha256-<digest>.att" (attestation kèm SBOM, trung bình
  # ~365 KB). Ở policy CŨ (tagStatus: any, count>50 — bản trước PR này), 2 tag
  # phụ này bị đếm CHUNG vào đúng 1 quỹ 50 với image ứng dụng: mỗi lần build ký
  # thành công tốn 3 slot (app + sig + att) thay vì 1, nên quỹ "50" thực chất chỉ
  # chứa được ~16-17 lần build thật — đẩy nhanh việc xóa nhầm digest đang chạy.
  #
  # Ở policy per-service này, pattern "*-${svc}" neo cuối chuỗi nên KHÔNG khớp
  # "sha256-....sig"/".att" (không kết thúc bằng "-<service>") — 2 tag phụ này
  # không bị rule nào chọn nên KHÔNG bao giờ bị xóa, tồn tại vô thời hạn. Đây là
  # đánh đổi có chủ đích, không phải sơ sót: dung lượng 1 cặp .sig+.att trung
  # bình chỉ ~365 KB (~$0.10/GB-tháng của ECR ⇒ ~$0.035/tháng cho mỗi 1.000 cặp
  # tích lũy) — không đáng kể so với rủi ro xóa nhầm chữ ký của 1 image còn sống
  # nếu áp expiry theo tuổi cho các tag này.
}

resource "aws_ecr_lifecycle_policy" "techx_corp_policy" {
  repository = aws_ecr_repository.techx_corp.name
  policy     = jsonencode({ rules = local.ecr_lifecycle_rules })
}
