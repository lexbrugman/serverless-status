# The values that make this instance yours. Day-to-day check changes live
# in checks.auto.tfvars, account membership in orgs.auto.tfvars; this file
# changes when the site itself does — or when an org joins or leaves.
locals {
  domain        = "status.example.com"
  dns_zone_name = "example.com"

  site = {
    name        = "Example Corp"
    description = "Live availability of our services."
    timezone    = "Europe/Amsterdam"
    links = [
      { label = "example.com", url = "https://example.com" },
    ]
  }

  # All optional; defaults shown in the module. Uncomment to override.
  page = {}

  # Each org's slice of the checks, with the routing attribute stripped:
  # the checks module's contract is org-agnostic.
  org_checks = { for org in keys(var.orgs) : org => {
    for key, check in var.checks :
    key => { for attr, value in check : attr => value if attr != "org" }
    if check.org == org
  } }
}

# Every check must belong to a configured org.
resource "terraform_data" "check_orgs" {
  input = keys(var.orgs)

  lifecycle {
    precondition {
      condition     = alltrue([for check in values(var.checks) : contains(keys(var.orgs), check.org)])
      error_message = "checks reference unknown orgs: ${join(", ", [for key, check in var.checks : "${key} -> ${check.org}" if !contains(keys(var.orgs), check.org)])}. Add the org (orgs.auto.tfvars plus its per-org block) or fix the check."
    }
  }
}

# --- per-org block: example --------------------------------------------------
# One copy of this section per org key, together with its provider pair in
# providers.tf. Provider configurations cannot be created dynamically, so
# this duplication is the ceiling of what OpenTofu allows; everything else
# about an org — its checks, its budget, its credentials — follows from the
# org key.

data "grafana_cloud_stack" "example" {
  provider = grafana.example_cloud
  slug     = var.orgs["example"].stack_slug
}

# Synthetic Monitoring installation: the bootstrap that turns a stack into
# something probes can publish to. Lives in the root because the sm provider
# is configured from its outputs.
resource "grafana_cloud_access_policy" "example_sm_publish" {
  provider = grafana.example_cloud

  region       = data.grafana_cloud_stack.example.region_slug
  name         = "${var.orgs["example"].stack_slug}-sm-publish"
  display_name = "Synthetic Monitoring publisher (${var.orgs["example"].stack_slug})"
  scopes       = ["metrics:write", "stacks:read", "logs:write", "traces:write"]

  realm {
    type       = "stack"
    identifier = data.grafana_cloud_stack.example.id
  }
}

resource "grafana_cloud_access_policy_token" "example_sm_publish" {
  provider = grafana.example_cloud

  region           = data.grafana_cloud_stack.example.region_slug
  access_policy_id = grafana_cloud_access_policy.example_sm_publish.policy_id
  name             = "${var.orgs["example"].stack_slug}-sm-publish"
}

resource "grafana_synthetic_monitoring_installation" "example" {
  provider = grafana.example_cloud

  stack_id              = data.grafana_cloud_stack.example.id
  metrics_publisher_key = grafana_cloud_access_policy_token.example_sm_publish.token
}

# The ref is stamped from the release you cloned; see docs/setup-guide.md.
module "checks_example" {
  source = "github.com/lexbrugman/serverless-status//modules/checks?ref=master"

  providers = {
    grafana.cloud = grafana.example_cloud
    grafana.sm    = grafana.example_sm
  }

  stack_slug               = var.orgs["example"].stack_slug
  checks                   = local.org_checks["example"]
  monthly_execution_budget = var.orgs["example"].monthly_execution_budget

  sm_api_url      = grafana_synthetic_monitoring_installation.example.stack_sm_api_url
  sm_access_token = grafana_synthetic_monitoring_installation.example.sm_access_token

  depends_on = [grafana_synthetic_monitoring_installation.example]
}

# --- end per-org block -------------------------------------------------------

# The ref is stamped from the release you cloned; see docs/setup-guide.md.
module "renderer" {
  source = "github.com/lexbrugman/serverless-status//modules/renderer?ref=master"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  domain        = local.domain
  dns_zone_name = local.dns_zone_name
  site          = local.site
  page          = local.page

  # One entry per org module: the page consolidates every account, and each
  # account keeps its own billing and execution budget.
  check_manifests    = [module.checks_example.check_manifest]
  prometheus_sources = [module.checks_example.prometheus]

  page_version = var.page_version
}

output "distribution_domain" {
  description = "Verify the page and certificate here before touching DNS."
  value       = module.renderer.distribution_domain
}
