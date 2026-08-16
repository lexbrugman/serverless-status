variable "name" {
  description = "Stack slug, used to name what this module creates inside the stack."
  type        = string
}

variable "jobs" {
  description = "Check identities to alert on — the Prometheus job labels, which are the check keys."
  type        = list(string)
}

variable "prometheus" {
  description = "Where the probe results live, from the checks module: query URL, user, and read token. The token reaches the stack as a datasource credential and never a file."
  type = object({
    query_url = string
    user      = string
    token     = string
  })
  sensitive = true
}

variable "email_addresses" {
  description = "Who hears about a failing check."
  type        = list(string)
}

variable "down_for_minutes" {
  description = "How long a check stays failing before the alert fires. Long enough to outlast a single missed probe, short enough to matter."
  type        = number

  validation {
    condition     = var.down_for_minutes >= 1
    error_message = "down_for_minutes must be at least 1."
  }
}
