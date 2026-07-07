terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

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
    tags = {
      Owner       = "CDO_04"
      Team        = "CDO_04"
      Project     = "TF4"
      Environment = "Phase3"
    }
  }
}
