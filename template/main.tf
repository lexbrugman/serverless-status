# The values that make this instance yours. Day-to-day check changes live
# in checks.auto.tfvars; this file changes when the site itself does.
locals {
  domain        = "status.example.com"
  dns_zone_name = "example.com"
  stack_slug    = "examplecorp"

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
}

data "grafana_cloud_stack" "this" {
  provider = grafana.cloud
  slug     = local.stack_slug
}

# Synthetic Monitoring installation: the bootstrap that turns a stack into
# something probes can publish to. Lives in the root because the sm provider
# is configured from its outputs.
resource "grafana_cloud_access_policy" "sm_publish" {
  provider = grafana.cloud

  region       = data.grafana_cloud_stack.this.region_slug
  name         = "${local.stack_slug}-sm-publish"
  display_name = "Synthetic Monitoring publisher (${local.stack_slug})"
  scopes       = ["metrics:write", "stacks:read", "logs:write", "traces:write"]

  realm {
    type       = "stack"
    identifier = data.grafana_cloud_stack.this.id
  }
}

resource "grafana_cloud_access_policy_token" "sm_publish" {
  provider = grafana.cloud

  region           = data.grafana_cloud_stack.this.region_slug
  access_policy_id = grafana_cloud_access_policy.sm_publish.policy_id
  name             = "${local.stack_slug}-sm-publish"
}

resource "grafana_synthetic_monitoring_installation" "this" {
  provider = grafana.cloud

  stack_id              = data.grafana_cloud_stack.this.id
  metrics_publisher_key = grafana_cloud_access_policy_token.sm_publish.token
}

# The ref is stamped from the release you cloned; see docs/setup-guide.md.
module "checks" {
  source = "github.com/lexbrugman/serverless-status//modules/checks?ref=master"

  providers = {
    grafana.cloud = grafana.cloud
    grafana.sm    = grafana.sm
  }

  stack_slug = local.stack_slug
  checks     = var.checks
  site       = local.site
  page       = local.page

  depends_on = [grafana_synthetic_monitoring_installation.this]
}

# The ref is stamped from the release you cloned; see docs/setup-guide.md.
module "renderer" {
  source = "github.com/lexbrugman/serverless-status//modules/renderer?ref=master"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  domain        = local.domain
  dns_zone_name = local.dns_zone_name
  page_manifest = module.checks.page_manifest
  prometheus    = module.checks.prometheus
  page_version  = var.page_version
}

output "distribution_domain" {
  description = "Verify the page and certificate here before touching DNS."
  value       = module.renderer.distribution_domain
}
