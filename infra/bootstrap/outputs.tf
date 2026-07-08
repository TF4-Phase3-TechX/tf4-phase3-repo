# Owner: Huy Hoàng nhóm CDO_04
output "state_bucket_arn" {
  value = aws_s3_bucket.terraform_state.arn
}

output "lock_table_name" {
  value = aws_dynamodb_table.terraform_locks.name
}
