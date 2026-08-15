# Do not edit — wiring a template update overwrites. Your values live in
# the *.tfvars data files.
terraform {
  required_version = ">= 1.10"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = ">= 4.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }

  # A backend block cannot read variables; bucket and region arrive at
  # init: tofu init -backend-config=state.auto.tfvars
  backend "s3" {
    key          = "serverless-status.tfstate"
    use_lockfile = true
  }

  # The Grafana metrics-read tokens land in state as resource attributes;
  # client-side encryption is the answer. The aws_kms key provider is the
  # one-block upgrade that removes the passphrase secret entirely (~$1/month
  # for the customer-managed key).
  encryption {
    key_provider "pbkdf2" "passphrase" {
      passphrase = var.state_passphrase
    }

    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.passphrase
    }

    state {
      method   = method.aes_gcm.default
      enforced = true
    }

    plan {
      method   = method.aes_gcm.default
      enforced = true
    }
  }
}

provider "aws" {
  region = var.region
}

# ACM certificates for CloudFront must live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
