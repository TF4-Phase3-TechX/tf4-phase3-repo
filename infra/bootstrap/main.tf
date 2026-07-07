# Owner: Huy Hoàng nhóm CDO_04
# 1. Tạo S3 Bucket lưu trữ State File
resource "aws_s3_bucket" "terraform_state" {
  bucket        = var.state_bucket_name
  force_destroy = true # Cho phép xóa bucket khi hủy hạ tầng sandbox
}

# Bật Versioning để lưu lịch sử các phiên bản State file (khôi phục khi bị lỗi)
resource "aws_s3_bucket_versioning" "state_versioning" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Bật mã hóa phía máy chủ (Server-Side Encryption) cho bảo mật
resource "aws_s3_bucket_server_side_encryption_configuration" "state_encryption" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Chặn quyền truy cập public (Public Access Block) bảo mật file State
resource "aws_s3_bucket_public_access_block" "state_public_block" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 2. Tạo DynamoDB Table phục vụ cơ chế khóa State (Locking)
resource "aws_dynamodb_table" "terraform_locks" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Environment = "Phase3"
    Team        = "TF4"
  }
}
