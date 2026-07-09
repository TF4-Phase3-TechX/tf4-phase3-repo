resource "aws_accessanalyzer_analyzer" "main" {
  analyzer_name = "tf4-iam-analyzer"
  type          = "ACCOUNT"
}
