# The bucket the main root's state lives in — OpenTofu-managed, but by this
# separate root so the main stack can never delete its own state store as a
# side effect. This root's state is the local terraform.tfstate next to this
# file, committed to the repository: git is the one store that predates
# everything, and this state holds no secrets, only bucket metadata.
#
# Apply runs locally with admin credentials, once at bootstrap and rarely
# again; the daily drift workflow plans it read-only.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

# Must match the backend bucket in ../providers.tf and the state-access
# policy in ../ci.tf. A backend block cannot read variables, so the name is
# a literal in three places, filled by one search-and-replace at setup.
locals {
  state_bucket = "CHANGE-ME-state-bucket"
}

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket

  # The encrypted history of everything else lives in here; nothing may
  # remove it as a side effect of any plan.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
