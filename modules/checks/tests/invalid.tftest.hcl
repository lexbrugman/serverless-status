# Every input validation, asserted to actually reject invalid input — the
# automated counterpart of the mutation rule.

mock_provider "grafana" {
  alias = "cloud"
}

mock_provider "http" {}

override_data {
  target = data.http.sm_tenant
  values = {
    status_code   = 200
    response_body = "{\"limits\":{\"maxChecks\":100}}"
  }
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
    probes = { Amsterdam = 11 }
  }
}

variables {
  stack_slug               = "examplecorp"
  monthly_execution_budget = 90000
  sm_api_url               = "https://sm.example"
  sm_access_token          = "mock-sm-token"

  checks = {
    website = {
      display = "Website"
      group   = "Web"
      type    = "https"
      host    = "www.example.com"
    }
  }
}

run "rejects_unknown_type" {
  command = plan

  variables {
    checks = {
      website = { display = "W", group = "Web", type = "gopher", host = "www.example.com" }
    }
  }

  expect_failures = [var.checks]
}

run "rejects_scheme_or_path_in_host" {
  command = plan

  variables {
    checks = {
      website = { display = "W", group = "Web", type = "https", host = "https://www.example.com" }
    }
  }

  expect_failures = [var.checks]
}

run "rejects_path_on_non_http" {
  command = plan

  variables {
    checks = {
      mail = { display = "M", group = "Mail", type = "smtp", host = "mx1.example.com", path = "/x" }
    }
  }

  expect_failures = [var.checks]
}

run "rejects_port_on_ping" {
  command = plan

  variables {
    checks = {
      uplink = { display = "U", group = "Net", type = "ping", host = "gw.example.com", port = 7 }
    }
  }

  expect_failures = [var.checks]
}

run "rejects_sub_minute_frequency" {
  command = plan

  variables {
    checks = {
      website = { display = "W", group = "Web", type = "https", host = "www.example.com", frequency_minutes = 0 }
    }
  }

  expect_failures = [var.checks]
}

run "rejects_invalid_key" {
  command = plan

  variables {
    checks = {
      "Web Site" = { display = "W", group = "Web", type = "https", host = "www.example.com" }
    }
  }

  expect_failures = [var.checks]
}

run "rejects_empty_probe_locations" {
  command = plan

  variables {
    probe_locations = []
  }

  expect_failures = [var.probe_locations]
}
