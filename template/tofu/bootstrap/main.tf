# Do not edit — wiring a template update overwrites. Your values are read
# from the instance's state.tfbackend.
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

locals {
  state_backend = file("${path.module}/../../state.tfbackend")
  state_bucket  = regex("bucket\\s*=\\s*\"([^\"]*)\"", local.state_backend)[0]
  region        = regex("region\\s*=\\s*\"([^\"]*)\"", local.state_backend)[0]
}

provider "aws" {
  region = local.region
}

module "state_bucket" {
  source = "../wiring/state-bucket"

  state_bucket = local.state_bucket
}
