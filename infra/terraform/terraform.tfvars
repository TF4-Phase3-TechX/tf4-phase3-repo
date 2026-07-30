budget_notification_emails = ["ngonguyentruongan2907@gmail.com"]

# REL-35 temporary AZ-loss drill guardrail:
# target AZ is us-east-1b, so Spot replacement is restricted to us-east-1a.
# Revert this line after the drill to restore normal multi-AZ Spot capacity.
karpenter_arm64_spot_zones = ["us-east-1a"]
