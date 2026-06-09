terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket       = "medilink-tf-state-371454942267"
    key          = "medilink/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
  }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      Environment = "Production"
      Project     = "MediLink-Hub"
      ManagedBy   = "Terraform"
    }
  }
}
