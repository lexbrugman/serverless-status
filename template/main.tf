# Do not edit — wiring a template update overwrites. Your values live in
# the *.tfvars data files; the logic lives under wiring/; your structural
# files are org_<key>.tf and page.tf.

module "routing" {
  source = "./wiring/routing"

  checks   = var.checks
  org_keys = keys(var.orgs)
}

module "ci" {
  source = "./wiring/ci"

  github_repository = var.github_repository
  state_bucket      = var.bucket
}

output "plan_role_arn" {
  description = "For the PLAN_ROLE_ARN repository variable."
  value       = module.ci.plan_role_arn
}

output "apply_role_arn" {
  description = "For the APPLY_ROLE_ARN repository variable."
  value       = module.ci.apply_role_arn
}
