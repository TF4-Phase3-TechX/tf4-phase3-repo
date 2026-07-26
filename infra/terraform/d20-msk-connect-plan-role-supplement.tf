# Supplement permissions for tf4-github-actions-plan so Terraform plan can
# refresh state for MSK Connect resources (Custom Plugins, Worker Configurations, Connectors).
#
# The plan role's base policy lives in infra/bootstrap/github-actions-oidc.tf.
# Adding read-only permissions here avoids a bootstrap apply dependency while
# still keeping the change in version control and under Terraform management.

data "aws_iam_policy_document" "plan_role_msk_connect_read" {
  statement {
    sid    = "ReadMskConnectState"
    effect = "Allow"

    actions = [
      "kafkaconnect:DescribeCustomPlugin",
      "kafkaconnect:DescribeWorkerConfiguration",
      "kafkaconnect:DescribeConnector",
      "kafkaconnect:ListConnectors",
      "kafkaconnect:ListCustomPlugins",
      "kafkaconnect:ListWorkerConfigurations",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "plan_role_msk_connect_read" {
  name   = "MskConnectReadForPlan"
  role   = "tf4-github-actions-plan"
  policy = data.aws_iam_policy_document.plan_role_msk_connect_read.json
}
