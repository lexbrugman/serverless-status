# The page itself. The two lists grow by one entry per org_<key>.tf file:
# the page consolidates every account, and each account keeps its own
# billing and execution budget.

# The ref is stamped from the release you cloned; see docs/setup-guide.md.
module "renderer" {
  source = "github.com/lexbrugman/serverless-status//modules/renderer?ref=master"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  domain        = var.domain
  dns_zone_name = var.dns_zone_name
  site          = var.site
  page          = var.page

  check_manifests    = [module.checks_example.check_manifest]
  prometheus_sources = [module.checks_example.prometheus]

  page_version = var.page_version
}

output "distribution_domain" {
  description = "Verify the page and certificate here before touching DNS."
  value       = module.renderer.distribution_domain
}
