# Yours: the identity of this instance. Data files (*.tfvars) carry
# everything you personalise; the .tf files carry only wiring, so a
# template update can overwrite them without touching your configuration.
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

# All optional; defaults shown in the module.
page = {}

# The Grafana accounts feeding this page. Adding an org is: an entry here
# plus its token in the GRAFANA_CLOUD_TOKENS secret — CI regenerates
# org_<key>.tf and page.tf from this map on its next run (bin/sync.sh
# does the same locally). Removing one is the reverse; its checks then
# fail the plan until reassigned or deleted.
orgs = {
  example = {
    stack_slug = "examplecorp"

    # Synthetic Monitoring executions per month this account may spend —
    # the allowance its plan includes, or the overage its owner accepts.
    monthly_execution_budget = 90000
  }
}
