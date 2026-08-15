# Behavior of a valid configuration: target assembly, provider units,
# manifest resolution, and budget arithmetic — all offline via mocked
# providers (the real provider schema still validates every attribute).

mock_provider "grafana" {
  alias = "cloud"
}

mock_provider "grafana" {
  alias = "sm"
}

override_data {
  target = data.grafana_cloud_stack.this
  values = {
    id                 = "123456"
    region_slug        = "eu"
    prometheus_url     = "https://prometheus-prod-01-eu-west-0.grafana.net"
    prometheus_user_id = 987654
  }
}

override_data {
  target = data.grafana_synthetic_monitoring_probes.main
  values = {
    probes = { Amsterdam = 11, London = 12 }
  }
}

variables {
  stack_slug = "examplecorp"

  checks = {
    api = {
      display           = "API"
      group             = "Web"
      type              = "https"
      host              = "api.example.com"
      path              = "/health"
      latency_budget_ms = 800
      order             = 20
    }
    admin = {
      display = "Admin panel"
      group   = "Web"
      type    = "https"
      host    = "admin.example.com"
      port    = 8443
      order   = 10
    }
    mail-inbound = {
      display = "Inbound mail"
      group   = "Mail"
      type    = "smtp"
      host    = "mx1.example.com"
      order   = 5
    }
    office-uplink = {
      display = "Office connectivity"
      group   = "Network"
      type    = "ping"
      host    = "gw.example.com"
    }
  }
}

run "targets_and_units" {
  command = plan

  assert {
    condition     = grafana_synthetic_monitoring_check.http["api"].target == "https://api.example.com/health"
    error_message = "https target with default port must omit the port and keep the path"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.http["admin"].target == "https://admin.example.com:8443/"
    error_message = "non-default port must appear in the target"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.smtp["mail-inbound"].target == "mx1.example.com:25"
    error_message = "smtp target is host:port"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.ping["office-uplink"].target == "gw.example.com"
    error_message = "ping target is the bare host"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.http["api"].frequency == 300000 && grafana_synthetic_monitoring_check.http["api"].timeout == 5000
    error_message = "https defaults are 5 min / 5 s, expressed in milliseconds"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.ping["office-uplink"].frequency == 600000 && grafana_synthetic_monitoring_check.ping["office-uplink"].timeout == 3000
    error_message = "ping defaults are 10 min / 3 s, expressed in milliseconds"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.smtp["mail-inbound"].timeout == 10000
    error_message = "smtp default timeout is 10 s, expressed in milliseconds"
  }

  assert {
    condition     = grafana_synthetic_monitoring_check.http["api"].probes == toset([11])
    error_message = "probes must resolve location names to IDs"
  }
}

run "manifest_and_outputs" {
  command = plan

  assert {
    condition     = output.check_manifest.schema_version == 2
    error_message = "manifest schema_version must be 2"
  }

  assert {
    condition     = output.check_manifest.checks.admin.port == 8443 && output.check_manifest.checks.api.port == 443
    error_message = "manifest ports must resolve type defaults"
  }

  assert {
    condition     = output.check_manifest.checks.api.path == "/health" && output.check_manifest.checks["mail-inbound"].path == null
    error_message = "manifest path resolves for http(s) only"
  }

  assert {
    condition     = output.check_manifest.checks["office-uplink"].port == null
    error_message = "ping has no port in the manifest"
  }

  assert {
    condition     = output.monthly_executions == 30240
    error_message = "expected 3 checks at 5 min (8640 each) plus 1 at 10 min (4320) from one location"
  }

  assert {
    condition     = output.prometheus.query_url == "https://prometheus-prod-01-eu-west-0.grafana.net/api/prom"
    error_message = "prometheus query_url must be the stack URL plus /api/prom"
  }

  assert {
    condition     = output.prometheus.user == "987654"
    error_message = "prometheus user is the stack's Prometheus instance ID as a string"
  }
}

run "over_budget_fails_the_plan" {
  command = plan

  variables {
    monthly_execution_budget = 20000
  }

  expect_failures = [terraform_data.execution_budget]
}

run "unknown_probe_location_fails_the_plan" {
  command = plan

  variables {
    probe_locations = ["Atlantis"]
  }

  expect_failures = [terraform_data.probe_locations]
}
