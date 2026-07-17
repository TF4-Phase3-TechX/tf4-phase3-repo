# Owner: Huy Hoàng nhóm CDO_04
# Import EKS access entries that were created before this Terraform refactor.
# These blocks let CI adopt the existing resources instead of failing with ResourceInUseException.

import {
  to = module.security_slack_alerts.aws_ssm_parameter.slack_webhook
  id = "/security-alerts/slack-webhook-url"
}

import {
  to = aws_eks_access_entry.view["sso_audit_readonly_analyze"]
  id = "techx-tf4-cluster:arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882"
}

import {
  to = aws_eks_access_policy_association.view["sso_audit_readonly_analyze"]
  id = "techx-tf4-cluster#arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882#arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
}

import {
  to = aws_eks_access_entry.view["sso_cost_perf_readonly_alerting"]
  id = "techx-tf4-cluster:arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86"
}

import {
  to = aws_eks_access_policy_association.view["sso_cost_perf_readonly_alerting"]
  id = "techx-tf4-cluster#arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86#arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
}

import {
  to = aws_eks_access_entry.view["sso_sec_reliability_readonly_audit"]
  id = "techx-tf4-cluster:arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155"
}

import {
  to = aws_eks_access_policy_association.view["sso_sec_reliability_readonly_audit"]
  id = "techx-tf4-cluster#arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155#arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
}
