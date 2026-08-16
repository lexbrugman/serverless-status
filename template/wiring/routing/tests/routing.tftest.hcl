# Identity derivation and account routing, offline: this module declares no
# providers, so the whole contract is checkable from the config alone.

variables {
  grafana_org_keys = ["example", "acme"]

  checks = [
    { grafana_org = "example", type = "https", host = "www.example.com" },
    { grafana_org = "example", type = "https", host = "admin.example.com", port = 8443, display = "Admin" },
    { grafana_org = "acme", type = "smtp", host = "mx1.acme.test", alert = false },
    { grafana_org = "acme", type = "ping", host = "gw.acme.test" },
  ]
}

run "identity_comes_from_host_protocol_and_unusual_port" {
  command = plan

  assert {
    condition     = contains(keys(output.org_checks["example"]), "www-example-com-https")
    error_message = "a default-port check is identified by host and protocol alone"
  }

  assert {
    condition     = contains(keys(output.org_checks["example"]), "admin-example-com-8443-https")
    error_message = "a non-default port belongs in the identity: it is what separates two checks on one host"
  }

  assert {
    condition     = contains(keys(output.org_checks["acme"]), "gw-acme-test-ping")
    error_message = "every account gets its own slice, keyed by identity"
  }
}

run "display_defaults_to_the_host_and_routing_attributes_are_stripped" {
  command = plan

  assert {
    condition     = output.org_checks["example"]["www-example-com-https"].display == "www.example.com"
    error_message = "an unnamed check shows its host"
  }

  assert {
    condition     = output.org_checks["example"]["admin-example-com-8443-https"].display == "Admin"
    error_message = "a stated display name wins"
  }

  assert {
    condition = alltrue([
      for check in values(output.org_checks["acme"]) :
      !contains(keys(check), "grafana_org") && !contains(keys(check), "alert")
    ])
    error_message = "the checks module's contract is account-agnostic; routing attributes stay behind"
  }
}

run "alert_false_opts_a_check_out" {
  command = plan

  assert {
    condition     = join(",", output.org_alert_jobs["acme"]) == "gw-acme-test-ping"
    error_message = "alert: false keeps a check off the notification path, and only that check"
  }

  assert {
    condition     = length(output.org_alert_jobs["example"]) == 2
    error_message = "checks alert unless they opt out"
  }
}

run "two_checks_with_one_identity_fail_the_plan" {
  command = plan

  variables {
    checks = [
      { grafana_org = "example", type = "https", host = "www.example.com", path = "/one" },
      { grafana_org = "example", type = "https", host = "www.example.com", path = "/two" },
    ]
  }

  expect_failures = [terraform_data.check_identities]
}

run "an_unknown_account_fails_the_plan" {
  command = plan

  variables {
    checks = [
      { grafana_org = "nowhere", type = "https", host = "www.example.com" },
    ]
  }

  expect_failures = [terraform_data.check_orgs]
}
