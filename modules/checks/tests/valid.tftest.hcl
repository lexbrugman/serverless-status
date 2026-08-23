# Behavior of a valid configuration: target assembly, provider units,
# manifest resolution, and budget arithmetic — all offline via mocked
# providers (the real provider schema still validates every attribute).

mock_provider "grafana" {
  alias = "cloud"
}

mock_provider "http" {}

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

# The usage reads are file-level: every run plans the whole module, and a
# run that says nothing about them would reach the real API.
override_data {
  target = data.http.usage_datasource
  values = {
    status_code   = 200
    response_body = "{\"uid\":\"usage-uid\"}"
  }
}

override_data {
  target = data.http.series
  values = {
    status_code   = 200
    response_body = "{\"data\": {\"result\": [{\"metric\": {\"__name__\": \"grafanacloud_instance_active_series\"}, \"value\": [1, \"265\"]}, {\"metric\": {\"__name__\": \"grafanacloud_instance_metrics_limits\"}, \"value\": [1, \"15000\"]}]}}"
  }
}

override_data {
  target = data.grafana_synthetic_monitoring_probes.main
  values = {
    probes = { Frankfurt = 11, London = 12 }
  }
}

variables {
  stack_slug               = "examplecorp"
  monthly_execution_budget = 90000
  sm_api_url               = "https://sm.example"
  sm_access_token          = "mock-sm-token"

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

# Every run overrides data.http.sm_tenant itself: a file-level default
# alongside the run-level quota scenarios would draw a "global override
# ignored" warning on each of those runs.
run "targets_and_units" {
  command = plan

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":{\"maxChecks\":100}}"
    }
  }

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

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":{\"maxChecks\":100}}"
    }
  }

  assert {
    condition     = output.check_manifest.schema_version == 4
    error_message = "manifest schema_version must be 4"
  }

  # The renderer makes its verdict over a window that is a multiple of the
  # probe interval, so the resolved frequency travels with the check rather
  # than being assumed on the other side of the seam.
  assert {
    condition = (
      output.check_manifest.checks["api"].frequency_minutes == 5 &&
      output.check_manifest.checks["office-uplink"].frequency_minutes == 10
    )
    error_message = "the manifest states each check's resolved frequency, defaults included"
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

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":{\"maxChecks\":100}}"
    }
  }

  variables {
    monthly_execution_budget = 20000
  }

  expect_failures = [terraform_data.execution_budget]
}

run "unknown_probe_location_fails_the_plan" {
  command = plan

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":{\"maxChecks\":100}}"
    }
  }

  variables {
    probe_locations = ["Atlantis"]
  }

  expect_failures = [terraform_data.probe_locations]
}

run "checks_beyond_the_tenant_quota_fail_the_plan" {
  command = plan

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":{\"maxChecks\":2}}"
    }
  }

  expect_failures = [terraform_data.tenant_quota]
}

run "tenant_without_published_limits_passes" {
  command = plan

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":null}"
    }
  }
}

run "unreadable_tenant_fails_the_plan" {
  command = plan

  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 401
      response_body = "unauthorized"
    }
  }

  expect_failures = [terraform_data.tenant_quota]
}


# The one run that applies. The usage reads authenticate with a service
# account this module creates, so a plan that has not made it yet cannot
# know what they return — the reading is only ever a fact after an apply,
# which is exactly what it reports on.
run "series_usage_is_read_from_the_account" {
  command = apply

  # Stated here because a file-level override of an address some run also
  # overrides is ignored everywhere, and unreadable_tenant_fails_the_plan
  # overrides this one.
  override_data {
    target = data.http.sm_tenant
    values = {
      status_code   = 200
      response_body = "{\"limits\":{\"maxChecks\":100}}"
    }
  }

  assert {
    condition     = output.metrics_series.used == 265 && output.metrics_series.limit == 15000
    error_message = "the series reading is surfaced as used against the enforced ceiling"
  }
}
