# One-time setup: the versioned S3 bucket that holds the demo stack's Terraform state.
# Uses local state on purpose (it can't store its own state in the bucket it creates).

terraform {
  required_version = ">= 1.16"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "flare-demo" }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "state" {
  bucket        = "flare-demo-state-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # lets `terraform destroy` clean up after the hackathon
}

# Versioning: every `terraform apply` creates a new object version,
# which is how the tool reconstructs deploy history (deploy_changes).
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Keep old state versions for 30 days, then expire them (keeps storage cost at ~zero).
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
  depends_on = [aws_s3_bucket_versioning.state]
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}
