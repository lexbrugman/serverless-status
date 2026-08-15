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

  # The state bucket is managed by the separate bootstrap/ root (whose own
  # state is committed to this repository), so this configuration can never
  # delete its own state store. Native locking, no DynamoDB lock table.
  # The bucket name must match bootstrap/main.tf and ci.tf — a backend
  # block cannot read variables.
  backend "s3" {
    bucket       = "CHANGE-ME-state-bucket"
    key          = "serverless-status.tfstate"
    region       = "eu-west-1"
    use_lockfile = true
  }

  # The Grafana metrics-read token lands in state as a resource attribute;
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

provider "grafana" {
  alias                     = "cloud"
  cloud_access_policy_token = var.grafana_cloud_token
}

# The Synthetic Monitoring credentials come out of the installation resource
# in main.tf — one apply hands the credential from one control plane to the
# other, which is the reason this stack is OpenTofu in the first place.
provider "grafana" {
  alias           = "sm"
  sm_access_token = grafana_synthetic_monitoring_installation.this.sm_access_token
  sm_url          = grafana_synthetic_monitoring_installation.this.stack_sm_api_url
}

provider "aws" {
  region = "eu-west-1"
}

# ACM certificates for CloudFront must live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
