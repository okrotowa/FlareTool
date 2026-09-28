terraform {
  required_version = ">= 1.16"

  # Replace the bucket name with the `state_bucket` output from resources/bootstrap/.
  backend "s3" {
    bucket       = "flare-demo-state-732529885455"
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
    tags = { Project = "flare-demo" }
  }
}
