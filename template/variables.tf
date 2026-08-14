variable "grafana_cloud_token" {
  description = "Provisioning access policy token (scopes: accesspolicies:read|write|delete, stacks:read). Supplied as TF_VAR_grafana_cloud_token; never lands in a file."
  type        = string
  sensitive   = true
}

variable "state_passphrase" {
  description = "Client-side state encryption passphrase (>= 16 characters). Supplied as TF_VAR_state_passphrase."
  type        = string
  sensitive   = true
}

variable "page_version" {
  description = "Version rendered in the page footer — CI passes the pinned module ref."
  type        = string
  default     = null
}

variable "checks" {
  description = "Every monitored endpoint (see checks.auto.tfvars). Shape and validation live in the checks module."
  type        = any
}
