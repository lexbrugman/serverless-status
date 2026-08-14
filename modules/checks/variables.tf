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
  default     = ["Amsterdam"]

  validation {
    condition     = length(var.probe_locations) > 0
    error_message = "at least one probe location is required."
  }
}

variable "monthly_execution_budget" {
  description = "Hard plan-time ceiling on computed Synthetic Monitoring executions per month (Grafana Cloud free tier: 100000; the default keeps headroom because the arithmetic models Grafana's accounting rather than contracting with it)."
  type        = number
  default     = 90000
}

variable "smtp_ehlo_hostname" {
  description = "Hostname the SMTP dialogue announces in EHLO — normally the status page's own domain."
  type        = string
}

variable "site" {
  description = "Page identity, passed through to the renderer via the manifest."
  type = object({
    name        = string
    title       = optional(string)
    description = optional(string)
    timezone    = string # IANA; outage log and timestamps
    accent      = optional(string)
    logo_svg    = optional(string)
    links       = optional(list(object({ label = string, url = string })), [])
  })

  validation {
    condition     = var.site.accent == null || can(regex("^#[0-9a-fA-F]{6}$", coalesce(var.site.accent, "#000000")))
    error_message = "site.accent must be a #rrggbb hex color."
  }

  validation {
    condition     = length(var.site.timezone) > 0
    error_message = "site.timezone must be a non-empty IANA timezone name."
  }
}

variable "page" {
  description = "Page behavior knobs, passed through to the renderer via the manifest."
  type = object({
    history_days    = optional(number, 90)  # length of the uptime bars
    outage_log_days = optional(number, 30)  # reach of the derived incident list
    retention_days  = optional(number, 400) # DynamoDB TTL horizon
    refresh_seconds = optional(number, 60)  # meta-refresh and staleness threshold
  })
  default = {}

  validation {
    condition     = var.page.retention_days >= var.page.history_days
    error_message = "retention_days must be >= history_days — a page cannot promise more history than the table keeps."
  }

  validation {
    condition     = var.page.outage_log_days <= var.page.retention_days
    error_message = "outage_log_days must be <= retention_days."
  }
}
