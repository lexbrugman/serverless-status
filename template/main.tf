# Do not edit — wiring a template update overwrites. Everything you decide
# lives in config.yaml; the logic lives under wiring/; your generated
# structure is grafana_org_<key>.tf and page.tf.

locals {
  # One decode, one source of truth. Every module input below is a field of
  # this, so a typo in the file surfaces here rather than four layers down.
  config = yamldecode(file("${path.root}/config.yaml"))

  # Alerting is optional and its shape is stated once here, so an instance
  # that never mentions it reads the same as one that switched it off.
  alerting = merge(
    { email_addresses = [], down_for_minutes = 5 },
    try(local.config.alerting, {}),
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

output "plan_role_arn" {
  description = "The read-only role CI plans and drift-checks with; the workflows derive it rather than reading it here."
  value       = module.ci.plan_role_arn
}

output "apply_role_arn" {
  description = "The role CI applies with, stated once by hand as the APPLY_ROLE_ARN repository variable and managed from the adoption on."
  value       = module.ci.apply_role_arn
}
