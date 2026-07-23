# DO NOT MERGE.
# This intentionally invalid Terraform file exists only to prove Mandate 10:
# a PR with red CI must not be mergeable.

resource "aws_s3_bucket" "sec20_intentional_red_ci" {
  bucket =
}
