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

  # The SMTP conversation, executed by the probe as expect -> send ->
  # start_tls within each entry, entries in order. A server that accepts
  # connections but fails STARTTLS negotiation shows as down; the TLS
  # handshake completing is the validation, and the post-upgrade EHLO/QUIT
  # proves the secured channel actually speaks SMTP.
  #
  # ORDER HAZARD: the provider models query_response as a set and serializes
  # it in hash order, not declaration order. Step zero exists to verify the
  # stored dialogue against the SM API before anything downstream is built;
  # if the order arrives scrambled, these entries must be reworked (or the
  # provider fixed) before proceeding.
  smtp_dialogue = [
    { expect = "^220", send = "EHLO ${var.smtp_ehlo_hostname}", start_tls = false },
    { expect = "^250", send = "STARTTLS", start_tls = false },
    { expect = "^220", send = "", start_tls = true },
    { expect = "", send = "EHLO ${var.smtp_ehlo_hostname}", start_tls = false },
    { expect = "^250", send = "QUIT", start_tls = false },
  ]
}
