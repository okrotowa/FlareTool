terraform {
  required_version = ">= 1.16"

  # Replace the bucket name with the `state_bucket` output from bootstrap/.
  backend "s3" {
    bucket       = "tfpulse-demo-state-REPLACE_WITH_ACCOUNT_ID"
    key          = "demo/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "tfpulse-demo" }
  }
}
