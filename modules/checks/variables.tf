variable "checks" {
  description = "Every monitored endpoint, keyed by a stable identifier. The key becomes the Prometheus job label, the DynamoDB partition key component, and the resource address — a rename is a deliberate destroy-and-recreate."
  type = map(object({
    display           = string
    group             = string
    type              = string           # https | http | ping | smtp
    host              = string           # bare hostname: no scheme, port, or path
    port              = optional(number) # type default; forbidden for ping
    path              = optional(string) # http/https only, default "/"
    frequency_minutes = optional(number) # https/http/smtp 5, ping 10
    timeout_seconds   = optional(number) # https/http 5, ping 3, smtp 10
    order             = optional(number, 50)
    latency_budget_ms = optional(number) # exceeded while up -> amber "slow"
  }))

  validation {
    condition     = alltrue([for c in var.checks : contains(["https", "http", "ping", "smtp"], c.type)])
    error_message = "check.type must be one of: https, http, ping, smtp."
  }

  validation {
    condition     = alltrue([for k in keys(var.checks) : can(regex("^[a-z0-9][a-z0-9-]*$", k))])
    error_message = "check keys must match ^[a-z0-9][a-z0-9-]*$ — they become Prometheus job labels and resource addresses."
  }

  validation {
    condition     = alltrue([for c in var.checks : !can(regex("[:/]", c.host))])
    error_message = "host is a bare hostname — no scheme, port, or path. Use the port/path fields."
  }

  validation {
    condition     = alltrue([for c in var.checks : contains(["https", "http"], c.type) || c.path == null])
    error_message = "path applies to https/http checks only."
  }

  validation {
    condition     = alltrue([for c in var.checks : c.type != "ping" || c.port == null])
    error_message = "ping has no port."
  }

  validation {
    condition     = alltrue([for c in var.checks : c.frequency_minutes == null || coalesce(c.frequency_minutes, 1) >= 1])
    error_message = "frequency_minutes must be at least 1."
  }
}

variable "stack_slug" {
  description = "Slug of the existing Grafana Cloud stack (looked up, never created — the stack predates this module)."
  type        = string
}

variable "probe_locations" {
  description = "Synthetic Monitoring public probe location names to run every check from."
  type        = list(string)
  default     = ["Frankfurt"]

  validation {
    condition     = length(var.probe_locations) > 0
    error_message = "at least one probe location is required."
  }
}

variable "monthly_execution_budget" {
  description = "Hard plan-time ceiling on computed Synthetic Monitoring executions per month for this account — the allowance its plan includes, or the spend its owner accepts. Grafana exposes no API for this number, so it is declared; the arithmetic models Grafana's accounting rather than contracting with it, so keep headroom."
  type        = number
}

variable "sm_api_url" {
  description = "The stack's Synthetic Monitoring API URL (the installation's stack_sm_api_url); the tenant's quotas are read from it at plan time."
  type        = string
}

variable "sm_access_token" {
  description = "Synthetic Monitoring access token (the installation's sm_access_token), for the tenant quota lookup."
  type        = string
  sensitive   = true
}
