# Where alerting: and grafana_orgs: are declared.
#
# Every other part of config.yaml is already typed by whichever module
# receives it — site and page by the renderer, each check by the checks
# module — and a type declaration is what bin/ci-check-config.py reads to
# know which keys are real. These two had no typed consumer: the root
# merges them into plain maps, and a plain map accepts anything.
#
# So this is their declaration, not a copy of one. Nothing else states
# their shape.
terraform {
  required_version = ">= 1.10"
}

variable "alerting" {
  description = "What may appear under alerting: in config.yaml."
  type = object({
    email_addresses = optional(list(string), [])
  })
  default = {}
}

variable "grafana_orgs" {
  description = "What may appear under each entry of grafana_orgs: in config.yaml."
  type = map(object({
    stack_slug               = string
    monthly_execution_budget = number
  }))
}

output "alerting" {
  description = "alerting: with its defaults applied."
  value       = var.alerting
}

output "grafana_orgs" {
  description = "grafana_orgs: as declared."
  value       = var.grafana_orgs
}
