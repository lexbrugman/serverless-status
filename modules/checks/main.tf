data "grafana_cloud_stack" "this" {
  provider = grafana.cloud
  slug     = var.stack_slug
}

data "grafana_synthetic_monitoring_probes" "main" {
  provider = grafana.sm
}

# The quota Grafana will actually enforce, read from the tenant itself so
# the plan checks this account's own numbers, not an assumption. (The
# monthly execution allowance has no API anywhere — that one stays a
# declared budget.)
data "http" "sm_tenant" {
  url = "${var.sm_api_url}/api/v1/tenant"

  request_headers = {
    Authorization = "Bearer ${var.sm_access_token}"
  }

  retry {
    attempts = 2
  }
}

locals {
  sm_tenant = try(jsondecode(data.http.sm_tenant.response_body), {})
  # A tenant without a published limit skips the comparison; the API stays
  # the authority at apply.
  tenant_max_checks = try(local.sm_tenant.limits.maxChecks, 0)
}

resource "terraform_data" "tenant_quota" {
  input = local.tenant_max_checks

  lifecycle {
    precondition {
      condition     = data.http.sm_tenant.status_code == 200
      error_message = "tenant lookup at ${var.sm_api_url}/api/v1/tenant returned status ${data.http.sm_tenant.status_code} — the quota check needs a readable tenant."
    }

    precondition {
      condition     = local.tenant_max_checks <= 0 || length(var.checks) <= local.tenant_max_checks
      error_message = "${length(var.checks)} checks configured, but this account's tenant allows ${local.tenant_max_checks}. Remove checks or raise the account's limit."
    }
  }
}

# A typo'd location must fail the plan with the available names, not a bare
# missing-key error somewhere in a resource. Every check resource
# depends_on this guard: on the first bootstrap apply the probes read is
# deferred and the precondition only evaluates mid-apply, so without the
# ordering the checks would race it into the API with a filtered-empty
# probe list.
resource "terraform_data" "probe_locations" {
  input = var.probe_locations

  lifecycle {
    precondition {
      condition     = alltrue([for l in var.probe_locations : contains(keys(data.grafana_synthetic_monitoring_probes.main.probes), l)])
      error_message = "unknown probe location(s): ${join(", ", setsubtract(var.probe_locations, keys(data.grafana_synthetic_monitoring_probes.main.probes)))}. Available: ${join(", ", sort(keys(data.grafana_synthetic_monitoring_probes.main.probes)))}."
    }
  }
}

resource "grafana_synthetic_monitoring_check" "http" {
  provider = grafana.sm
  for_each = local.http_checks

  job       = each.key
  target    = local.targets[each.key]
  probes    = local.probe_ids
  frequency = local.frequency_ms[each.key]
  timeout   = local.timeout_ms[each.key]
  labels    = { group = each.value.group }

  settings {
    http {
      # An http check asserts nothing about TLS; an https check fails
      # without it.
      fail_if_not_ssl    = each.value.type == "https"
      valid_status_codes = [200]
    }
  }

  depends_on = [terraform_data.probe_locations]
}

resource "grafana_synthetic_monitoring_check" "ping" {
  provider = grafana.sm
  for_each = local.ping_checks

  job       = each.key
  target    = local.targets[each.key]
  probes    = local.probe_ids
  frequency = local.frequency_ms[each.key]
  timeout   = local.timeout_ms[each.key]
  labels    = { group = each.value.group }

  settings {
    ping {}
  }

  depends_on = [terraform_data.probe_locations]
}

# The STARTTLS conversation lives in its own module because two consumers
# need the identical list: this resource and the wire-payload guard
# (scripts/check-sm-payloads.py), which proves the provider still
# transmits it in order. See dialogue/main.tf for why the spellings are
# load-bearing.
module "smtp_dialogue" {
  source = "./dialogue"
}

resource "grafana_synthetic_monitoring_check" "smtp" {
  provider = grafana.sm
  for_each = local.smtp_checks

  job       = each.key
  target    = local.targets[each.key]
  probes    = local.probe_ids
  frequency = local.frequency_ms[each.key]
  timeout   = local.timeout_ms[each.key]
  labels    = { group = each.value.group }

  settings {
    tcp {
      # The connection starts plaintext; TLS arrives via STARTTLS inside
      # the dialogue, which is the thing being tested.
      tls = false

      dynamic "query_response" {
        for_each = module.smtp_dialogue.entries
        content {
          expect    = query_response.value.expect
          send      = query_response.value.send
          start_tls = query_response.value.start_tls
        }
      }
    }
  }

  depends_on = [terraform_data.probe_locations]
}

# Read credentials for the renderer, scoped to exactly this stack's metrics.
# The token is handed over through the module seam and SSM only — it never
# touches GitHub, a file, or a shell.
resource "grafana_cloud_access_policy" "metrics_read" {
  provider = grafana.cloud

  region       = data.grafana_cloud_stack.this.region_slug
  name         = "${var.stack_slug}-status-metrics-read"
  display_name = "Status page metrics read (${var.stack_slug})"
  scopes       = ["metrics:read"]

  realm {
    type       = "stack"
    identifier = data.grafana_cloud_stack.this.id
  }
}

resource "grafana_cloud_access_policy_token" "metrics_read" {
  provider = grafana.cloud

  region           = data.grafana_cloud_stack.this.region_slug
  access_policy_id = grafana_cloud_access_policy.metrics_read.policy_id
  name             = "${var.stack_slug}-status-metrics-read"
}

# Alerting lives inside the stack, which a cloud access policy token cannot
# reach: it mints a stack-scoped service account instead, and the root
# configures a provider from it. Minted whether or not alerting is
# configured, because a provider configuration must be evaluable even when
# nothing uses it.
resource "grafana_cloud_stack_service_account" "alerting" {
  provider = grafana.cloud

  stack_slug = var.stack_slug
  name       = "${var.stack_slug}-status-alerting"
  role       = "Admin"
}

resource "grafana_cloud_stack_service_account_token" "alerting" {
  provider = grafana.cloud

  stack_slug         = var.stack_slug
  service_account_id = grafana_cloud_stack_service_account.alerting.id
  name               = "${var.stack_slug}-status-alerting"
}
