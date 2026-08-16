variable "domain" {
  description = "Hostname the status page is served on (also names the bucket, table, and function)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.domain))
    error_message = "domain must be a bare DNS name, e.g. status.example.com."
  }
}

variable "dns_zone_name" {
  description = "Name of the pre-existing Route 53 hosted zone (looked up by name so a typo fails loudly; a typo'd zone ID could quietly resolve to a real zone that isn't yours)."
  type        = string
}

variable "manage_dns" {
  description = "Create the validation and alias records in the zone. When false, the records are emitted as outputs for an externally-managed zone."
  type        = bool
  default     = true
}

variable "site" {
  description = "Page identity — the renderer's own concern, not any one stack's."
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
  description = "Page behavior knobs."
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

variable "check_manifests" {
  description = "Each checks module's check_manifest output — the seam between the modules. A list so one page can consolidate several Grafana accounts (each stack keeps its own billing); one entry is the common case."
  type        = any
}

variable "prometheus_sources" {
  description = "Each checks module's prometheus output; the handler queries every source and merges by job. Stored only in SSM."
  type = list(object({
    query_url = string
    user      = string
    token     = string
  }))
  sensitive = true
}

locals {
  check_keys = flatten([for manifest in var.check_manifests : keys(manifest.checks)])
  checks     = merge([for manifest in var.check_manifests : manifest.checks]...)
}

# The renderer asserts the seam so a half-merged ref bump — or two stacks
# claiming the same check key — fails as a plan-time sentence instead of a
# baffling runtime error.
resource "terraform_data" "manifest_compatibility" {
  input = [for manifest in var.check_manifests : manifest.schema_version]

  lifecycle {
    precondition {
      condition     = alltrue([for manifest in var.check_manifests : manifest.schema_version == 2])
      error_message = "a check_manifest has a schema_version other than 2 — pin every module to the same ref."
    }

    precondition {
      condition     = length(local.check_keys) == length(distinct(local.check_keys))
      error_message = "check keys collide across manifests: ${join(", ", [for k in distinct(local.check_keys) : k if length([for x in local.check_keys : x if x == k]) > 1])}. Keys are Prometheus job labels and DynamoDB partition keys; they must be unique across every stack feeding this page."
    }
  }
}

variable "page_version" {
  description = "Release version rendered in the page footer."
  type        = string
  default     = null
}

variable "page_source" {
  description = "Repository the page is built from, as owner/name — the footer links the version to its release there. Null renders the version as plain text."
  type        = string
  default     = null
}
