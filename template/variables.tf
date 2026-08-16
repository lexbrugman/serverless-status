# Do not edit — wiring a template update overwrites. What you decide lives
# in status.yaml; what is left here is what must never be written to a
# file: the secrets, and the identity CI reads from its own token.

variable "github_repository" {
  description = "This instance repository as the OIDC token's sub claim spells it, resolved from the token by the workflows and supplied as TF_VAR_github_repository; never configured, because a configured spelling can disagree with the issuer's."
  type        = string
}

variable "grafana_cloud_tokens" {
  description = "Provisioning access policy token per Grafana account key (scopes: accesspolicies:read|write|delete, stacks:read). Supplied as TF_VAR_grafana_cloud_tokens='{ example = \"...\" }'; never lands in a file."
  type        = map(string)
  sensitive   = true
}

variable "state_passphrase" {
  description = "Client-side state encryption passphrase — created once at setup (>= 16 characters), kept in a password manager, supplied as TF_VAR_state_passphrase. Every plan and apply needs the same value; a lost passphrase is unrecoverable state."
  type        = string
  sensitive   = true
}
