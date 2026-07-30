budget_notification_emails = ["ngonguyentruongan2907@gmail.com"]

# REL-35 temporary AZ-loss drill guardrail:
# target AZ is us-east-1b, so replacement capacity is restricted away from us-east-1b.
# Revert these lines after the drill to restore normal multi-AZ capacity.
karpenter_arm64_spot_zones       = ["us-east-1a"]
karpenter_arm64_protected_zones  = ["us-east-1a"]
managed_node_group_arm64_1b_size = 0
