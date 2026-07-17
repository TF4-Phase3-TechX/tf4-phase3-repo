resource "aws_security_group" "test_fail_sg" {
  name        = "test-fail-sg"
  description = "Security group for testing tfsec failure"
  vpc_id      = "vpc-12345678"

  ingress {
    description = "SSH open to the world"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # This should fail tfsec high severity checks
  }
}
