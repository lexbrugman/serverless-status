# Do not edit — wiring a template update overwrites. Your values live in
# the *.tfvars data files; the logic lives under wiring/; your structural
# files are org_<key>.tf and page.tf.

# The version in the page footer is the release the modules are pinned to,
# read from the pin itself rather than passed in by whatever ran OpenTofu:
# a CI-injected value is absent from every other plan, and reads as drift
# on the renderer's environment on every scheduled run. A root whose
# module sources point at local paths has no release to name.
locals {
  page_version = try(regex("[?]ref=([^\"]*)\"", file("${path.root}/page.tf"))[0], "local")
}

module "routing" {
  source = "./wiring/routing"

  checks   = var.checks
  org_keys = keys(var.orgs)
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
