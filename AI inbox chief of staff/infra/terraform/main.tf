terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    # Configure per environment:
    # bucket = "inbox-terraform-state-<account_id>"
    # key    = "inbox-chief-of-staff/<env>/terraform.tfstate"
    # region = "us-east-1"
    # encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "inbox-chief-of-staff"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "${var.app_name}-${var.environment}"
}
