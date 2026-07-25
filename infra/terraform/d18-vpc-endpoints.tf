# Security Group for VPC Interface Endpoints (Allow HTTPS 443 from VPC CIDR) - CDO_04
resource "aws_security_group" "vpc_endpoints" {
  name        = "tf4-d18-vpc-endpoints-sg"
  description = "Security Group for VPC Interface Endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS inbound from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "HTTPS outbound to VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "tf4-d18-vpc-endpoints-sg"
    }
  )
}

# 1. Gateway Endpoint for S3 (linked to private route tables)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids

  tags = merge(
    var.tags,
    {
      Name = "tf4-d18-s3-gateway"
    }
  )
}

# 2. Interface Endpoints: ECR API, ECR DKR, STS, Logs, SSM, SSM Messages, EC2 Messages
locals {
  interface_services = [
    "ecr.api",
    "ecr.dkr",
    "sts",
    "logs",
    "ssm",
    "ssmmessages",
    "ec2messages"
  ]
}

resource "aws_vpc_endpoint" "interfaces" {
  for_each            = toset(local.interface_services)
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.tags,
    {
      Name = "tf4-d18-interface-${each.key}"
    }
  )
}

# 3. VPC Flow Logs to CloudWatch Logs (with 7 days retention)
resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  name              = "/aws/vpc-flow-logs/techx-vpc"
  retention_in_days = 7

  tags = var.tags
}

resource "aws_iam_role" "vpc_flow_logs" {
  name = "tf4-d18-vpc-flow-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "vpc-flow-logs.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "vpc_flow_logs" {
  name = "tf4-d18-vpc-flow-logs-policy"
  role = aws_iam_role.vpc_flow_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ]
      Resource = "${aws_cloudwatch_log_group.vpc_flow_logs.arn}:*"
    }]
  })
}

resource "aws_flow_log" "techx_vpc" {
  iam_role_arn    = aws_iam_role.vpc_flow_logs.arn
  log_destination = aws_cloudwatch_log_group.vpc_flow_logs.arn
  traffic_type    = "ALL"
  vpc_id          = module.vpc.vpc_id

  tags = merge(
    var.tags,
    {
      Name = "tf4-d18-vpc-flow-log"
    }
  )
}
