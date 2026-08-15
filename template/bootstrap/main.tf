# Do not edit — wiring a template update overwrites. Your values live in
# terraform.tfvars beside this file.
#
# A separate root so the main stack can never delete its own state store.
# Its state is the local terraform.tfstate next to this file, committed to
# the repository: git is the one store that predates everything, and this
# state holds no secrets, only bucket metadata. Apply runs locally with
# admin credentials, once at bootstrap and rarely again; the daily drift
# workflow plans it read-only.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

variable "state_bucket" {
  description = "Name of the state bucket; must match backend.tfvars and instance.auto.tfvars in the root above."
  type        = string
}

variable "aws_region" {
  description = "Region the bucket lives in."
  type        = string
}

provider "aws" {
  region = var.aws_region
}

module "state_bucket" {
  source = "../wiring/state-bucket"

  state_bucket = var.state_bucket
}
