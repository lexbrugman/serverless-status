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

variable "page_manifest" {
  description = "The checks module's page_manifest output — the seam between the two modules."
  type        = any
}

# The renderer asserts the seam's schema version so a half-merged ref bump
# fails as a plan-time sentence instead of a baffling runtime error.
resource "terraform_data" "manifest_compatibility" {
  input = var.page_manifest.schema_version

  lifecycle {
    precondition {
      condition     = var.page_manifest.schema_version == 1
      error_message = "page_manifest schema_version ${var.page_manifest.schema_version} is not supported by this renderer — pin both modules to the same ref."
    }
  }
}

variable "prometheus" {
  description = "The checks module's prometheus output: query endpoint and read credentials, stored only in SSM."
  type = object({
    query_url = string
    user      = string
    token     = string
  })
  sensitive = true
}

variable "page_version" {
  description = "Release version rendered in the page footer."
  type        = string
  default     = null
}
