# Owner: Huy Hoàng nhóm CDO_04
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend bucket/region must match bootstrap output.
  # After bootstrap apply, uncomment and run: terraform init -reconfigure
  backend "s3" {
    bucket         = "tf4-phase3-state-bucket-511825856493"
    key            = "eks/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "tf4-phase3-state-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

data "aws_caller_identity" "current" {}
