# Yours: the identity of this instance. Data files (*.tfvars) carry
# everything you personalise; the .tf files carry only wiring, so a
# template update can overwrite them without touching your configuration.
domain        = "status.example.com"
dns_zone_name = "example.com"
aws_region    = "eu-west-1"

# owner/name of this instance repository (CI trust) and the state bucket
# (must match backend.tfvars and bootstrap/terraform.tfvars).
github_repository = "example-org/serverless-status-instance"
state_bucket      = "CHANGE-ME-state-bucket"

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
