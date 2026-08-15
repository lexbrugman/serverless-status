data "grafana_cloud_stack" "this" {
  provider = grafana.cloud
  slug     = var.stack_slug
}

data "grafana_synthetic_monitoring_probes" "main" {
  provider = grafana.sm
}

# A typo'd location must fail the plan with the available names, not a bare
# missing-key error somewhere in a resource.
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
