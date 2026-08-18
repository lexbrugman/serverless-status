# Do not edit — wiring a template update overwrites. Everything decided
# lives in config.yaml, one directory up; the logic lives under wiring/,
# and the generated structure beside this file is grafana_org_<key>.tf and
# page.tf.

locals {
  # One decode, one source of truth. Every module input below is a field of
  # this, so a typo in the file surfaces here rather than four layers down.
  config = yamldecode(file("${path.root}/../config.yaml"))

  # Alerting is optional; wiring/config declares its shape and applies the
  # default, so an instance that never mentions it reads the same as one
  # that switched it off.
  alerting = module.config.alerting

  # What "down" means, resolved once here because two consumers need the
  # identical answer: the renderer's own query and the alert rule. The
  # defaults mirror modules/renderer's `page` variable and are pinned to it
  # by scripts/check-cross-layer.py.
  page = merge(
    { down_window_multiple = 3, down_quorum = 0.5 },
    try(local.config.page, {}),
  )

  # The version in the page footer is the release the modules are pinned to,
  # read from the pin itself rather than passed in by whatever ran OpenTofu:
  # a CI-injected value is absent from every other plan, and reads as drift
  # on the renderer's environment on every scheduled run. A root whose
  # module sources point at local paths has no release to name.
  page_version = try(regex("[?]ref=([^\"]*)\"", file("${path.root}/page.tf"))[0], "local")

  # The footer links back to what built the page, taken from the same pin:
  # a fork links to the fork, and nothing repeats the repository by hand.
  page_source = try(regex("\"github.com/([^/]*/[^/]*)//modules/", file("${path.root}/page.tf"))[0], null)
}

# Declares the two levels of config.yaml no other module types, so every
# part of the file has a declaration bin/ci-check-config.py can read.
module "config" {
  source = "./wiring/config"

  alerting     = try(local.config.alerting, {})
  grafana_orgs = local.config.grafana_orgs
}

module "routing" {
  source = "./wiring/routing"

  checks           = local.config.checks
  grafana_org_keys = keys(local.config.grafana_orgs)
}

module "ci" {
  source = "./wiring/ci"

  github_repository = var.github_repository
  state_bucket      = local.state_bucket
}

# The file exactly as it was read, so the unknown-key check can compare it
# against the type constraints in the same plan JSON. Emitted rather than
# re-parsed: a second reader of config.yaml is a second answer to what it
# says.
output "config_as_read" {
  description = "config.yaml as yamldecode returned it, for bin/ci-check-config.py."
  value       = local.config
}

output "plan_role_arn" {
  description = "The read-only role CI plans and drift-checks with; the workflows derive it rather than reading it here."
  value       = module.ci.plan_role_arn
}

output "apply_role_arn" {
  description = "The role CI applies with, stated once by hand as the APPLY_ROLE_ARN repository variable and managed from the adoption on."
  value       = module.ci.apply_role_arn
}
