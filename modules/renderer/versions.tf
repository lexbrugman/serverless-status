terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
      # ACM certificates for CloudFront must live in us-east-1; everything
      # else uses the default provider. Both are configured in the root —
      # a module that configures its own providers breaks for_each and
      # makes clean destroys impossible.
      configuration_aliases = [aws.us_east_1]
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
  }
}
