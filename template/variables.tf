# Do not edit — wiring a template update overwrites. Values live in the
# *.tfvars data files and, for the secrets, in the environment.

variable "domain" {
  description = "Hostname the status page is served on."
  type        = string
}

variable "dns_zone_name" {
  description = "Name of the pre-existing Route 53 hosted zone."
  type        = string
}

variable "aws_region" {
  description = "Region the renderer lives in."
  type        = string
}

variable "github_repository" {
  description = "owner/name of this instance repository, for CI's OIDC trust."
  type        = string
}

variable "state_bucket" {
  description = "Name of the state bucket; must match backend.tfvars and bootstrap/terraform.tfvars."
  type        = string
}

variable "site" {
  description = "Page identity (see instance.auto.tfvars); shape and validation live in the renderer module."
  type        = any
}

variable "page" {
  description = "Page behavior overrides (see instance.auto.tfvars); shape and validation live in the renderer module."
  type        = any
}

variable "orgs" {
  description = "The Grafana Cloud accounts feeding this page, keyed by a stable org identifier — one account per organisation, each keeping its own billing and execution budget. Provider configurations cannot be created dynamically, so each key also has one org_<key>.tf file (copied from org_example.tf) and its entries in page.tf."
  type = map(object({
    stack_slug               = string
    monthly_execution_budget = number
  }))
}

variable "grafana_cloud_tokens" {
  description = "Provisioning access policy token per org key (scopes: accesspolicies:read|write|delete, stacks:read). Supplied as TF_VAR_grafana_cloud_tokens='{ example = \"...\" }'; never lands in a file."
  type        = map(string)
  sensitive   = true
}

variable "state_passphrase" {
  description = "Client-side state encryption passphrase — created once at setup (>= 16 characters), kept in a password manager, supplied as TF_VAR_state_passphrase. Every plan and apply needs the same value; a lost passphrase is unrecoverable state."
  type        = string
  sensitive   = true
}

variable "page_version" {
  description = "Version rendered in the page footer — CI passes the pinned module ref."
  type        = string
  default     = null
}

variable "checks" {
  description = "Every monitored endpoint (see checks.auto.tfvars). Each entry names the org whose account runs it; the remaining shape and validation live in the checks module."
  type        = any
}
