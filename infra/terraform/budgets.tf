# Owner: Huy Hoàng nhóm CDO_04
resource "aws_budgets_budget" "monthly_cost" {
  name         = "techx-tf4-monthly-cost-budget"
  budget_type  = "COST"
  limit_amount = var.budget_monthly_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = length(var.budget_notification_emails) > 0 ? toset([70, 90, 100]) : []

    content {
      comparison_operator        = "GREATER_THAN"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.budget_notification_emails
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
    }
  }

  tags = var.tags
}
