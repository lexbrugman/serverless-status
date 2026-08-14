locals {
  port_default = { https = 443, http = 80, smtp = 25 }

  freq_default    = { https = 5, http = 5, smtp = 5, ping = 10 }
  timeout_default = { https = 5, http = 5, smtp = 10, ping = 3 }

  # The one place a target string is ever assembled (the type is the
  # protocol; host, port, and path stay separate facts everywhere else).
  targets = { for k, c in var.checks : k => (
    contains(["https", "http"], c.type)
    ? "${c.type}://${c.host}${coalesce(c.port, local.port_default[c.type]) == local.port_default[c.type] ? "" : ":${c.port}"}${coalesce(c.path, "/")}"
    : c.type == "smtp" ? "${c.host}:${coalesce(c.port, local.port_default.smtp)}"
    : c.host
  ) }

  # Provider units: frequency and timeout are milliseconds.
  frequency_ms = { for k, c in var.checks : k => coalesce(c.frequency_minutes, local.freq_default[c.type]) * 60 * 1000 }
  timeout_ms   = { for k, c in var.checks : k => coalesce(c.timeout_seconds, local.timeout_default[c.type]) * 1000 }

  http_checks = { for k, c in var.checks : k => c if contains(["https", "http"], c.type) }
  ping_checks = { for k, c in var.checks : k => c if c.type == "ping" }
  smtp_checks = { for k, c in var.checks : k => c if c.type == "smtp" }

  # Unknown locations are filtered rather than indexed so the plan reaches
  # terraform_data.probe_locations, whose precondition names the typo and
  # lists what is available.
  probe_ids = [
    for location in var.probe_locations :
    data.grafana_synthetic_monitoring_probes.main.probes[location]
    if contains(keys(data.grafana_synthetic_monitoring_probes.main.probes), location)
  ]

}
