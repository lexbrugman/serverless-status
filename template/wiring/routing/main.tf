# Routes each check to the org whose account runs it, stripping the
# routing attribute: the checks module's contract is org-agnostic.
terraform {
  required_version = ">= 1.10"
}

variable "checks" {
  description = "The full check map, each entry carrying `org`."
  type        = any
}

variable "org_keys" {
  description = "The configured org identifiers."
  type        = set(string)
}

# Every check must belong to a configured org.
resource "terraform_data" "check_orgs" {
  input = var.org_keys

  lifecycle {
    precondition {
      condition     = alltrue([for check in values(var.checks) : contains(var.org_keys, check.org)])
      error_message = "checks reference unknown orgs: ${join(", ", [for key, check in var.checks : "${key} -> ${check.org}" if !contains(var.org_keys, check.org)])}. Add the org (the orgs map plus its org_<key>.tf file) or fix the check."
    }
  }
}

output "org_checks" {
  description = "Each org's slice of the checks, org attribute stripped."
  value = { for org in var.org_keys : org => {
    for key, check in var.checks :
    key => { for attr, value in check : attr => value if attr != "org" }
    if check.org == org
  } }
}
