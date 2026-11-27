terraform {
  required_version = ">= 1.10.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {}
}
provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.name, Environment = var.environment, ManagedBy = "Terraform", DataClass = "Synthetic" }
  }
}
