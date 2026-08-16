# Turns the checks list into what the checks module takes: a map keyed by
# each check's identity, split per Grafana account, with the routing
# attributes stripped. The module's contract is org-agnostic and keyed.
terraform {
  required_version = ">= 1.10"
}

variable "checks" {
  description = "The checks list exactly as config.yaml states it."
  type        = any
}

variable "grafana_org_keys" {
  description = "The configured Grafana account identifiers."
  type        = set(string)
}

locals {
  # A check is identified by the host it watches, the port when that is not
  # the protocol's own, and the protocol — never by a name somebody had to
  # invent. An identity is a history, so the split follows what an edit
  # means: a path is a detail of one target (/health to /healthz keeps its
  # history), while a non-default port is what makes an admin panel a
  # different service from the site beside it. Only two checks alike in all
  # three need a `key:`, and that is rare enough to be worth an error
  # rather than a name on every check.
  default_ports = { https = 443, http = 80, smtp = 25 }

  identified = [
    for check in var.checks : merge(check, {
      key = try(check.key, null) != null ? check.key : join("-", compact([
        replace(lower(check.host), ".", "-"),
        try(check.port, null) == null || try(check.port, null) == lookup(local.default_ports, check.type, null) ? "" : tostring(check.port),
        check.type,
      ]))
      display = try(check.display, null) != null ? check.display : check.host
    })
  ]

  # Grouped rather than keyed directly: a duplicate would otherwise fail
  # deep inside a for expression, naming neither check.
  grouped = { for check in local.identified : check.key => check... }

  duplicates = [for key, group in local.grouped : key if length(group) > 1]

  by_key = { for key, group in local.grouped : key => group[0] }

  routing_attributes = ["key", "grafana_org", "alert"]
}

resource "terraform_data" "check_identities" {
  input = keys(local.by_key)

  lifecycle {
    precondition {
      condition     = length(local.duplicates) == 0
      error_message = "these checks share an identity: ${join(", ", local.duplicates)}. Two checks on one host speaking one protocol — two paths on a site, say — need a `key:` on at least one to tell them apart."
    }

    precondition {
      condition     = alltrue([for check in local.identified : can(regex("^[a-z0-9][a-z0-9-]*$", check.key))])
      error_message = "these hosts cannot produce a check identity: ${join(", ", [for check in local.identified : check.host if !can(regex("^[a-z0-9][a-z0-9-]*$", check.key))])}. The identity becomes a Prometheus job label and a resource address, so a host must be a plain name."
    }
  }
}

# Every check must belong to a configured Grafana account.
resource "terraform_data" "check_orgs" {
  input = var.grafana_org_keys

  lifecycle {
    precondition {
      condition     = alltrue([for check in local.identified : contains(var.grafana_org_keys, check.grafana_org)])
      error_message = "checks reference unknown Grafana accounts: ${join(", ", [for check in local.identified : "${check.key} -> ${check.grafana_org}" if !contains(var.grafana_org_keys, check.grafana_org)])}. Add the account to grafana_orgs or fix the check."
    }
  }
}

output "org_checks" {
  description = "Each account's slice of the checks, keyed by identity, routing attributes stripped."
  value = { for org in var.grafana_org_keys : org => {
    for key, check in local.by_key :
    key => { for name, value in check : name => value if !contains(local.routing_attributes, name) }
    if check.grafana_org == org
  } }
}

output "org_alert_jobs" {
  description = "Each account's checks that alert, by identity — alert: false opts one out."
  value = { for org in var.grafana_org_keys : org => sort([
    for key, check in local.by_key : key
    if check.grafana_org == org && try(check.alert, true)
  ]) }
}
