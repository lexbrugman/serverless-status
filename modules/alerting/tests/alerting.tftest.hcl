# What the rule asks Prometheus and where the answer goes — offline, via
# mocked providers. Delivery itself is not assertable here: that a message
# reaches a mailbox is Grafana's to do and a human's to confirm.

mock_provider "grafana" {
  alias = "stack"
}

variables {
  name             = "examplecorp"
  jobs             = ["api-example-com-https", "mx1-example-com-smtp"]
  email_addresses  = ["ops@example.com"]
  down_for_minutes = 5

  prometheus = {
    query_url = "https://prometheus-prod-01-eu-west-0.grafana.net/api/prom"
    user      = "987654"
    token     = "mock-read-token"
  }
}

run "the_rule_watches_every_alerting_check" {
  command = plan

  assert {
    condition = strcontains(
      jsondecode(grafana_rule_group.down.rule[0].data[0].model).expr,
      "job=~\"^(api-example-com-https|mx1-example-com-smtp)$\""
    )
    error_message = "one rule covers every alerting check; Grafana fans it out per job"
  }

  assert {
    condition     = jsondecode(grafana_rule_group.down.rule[0].data[0].model).instant == true
    error_message = "the current value decides, not an average over a window"
  }
}

run "it_fires_only_after_the_configured_wait" {
  command = plan

  assert {
    condition     = grafana_rule_group.down.rule[0].for == "5m"
    error_message = "a single missed probe must not page anyone"
  }

  assert {
    condition = (
      jsondecode(grafana_rule_group.down.rule[0].data[1].model).conditions[0].evaluator.type == "lt" &&
      tonumber(jsondecode(grafana_rule_group.down.rule[0].data[1].model).conditions[0].evaluator.params[0]) == 1
    )
    error_message = "the alert condition is probe_success below 1"
  }

  assert {
    condition     = grafana_rule_group.down.rule[0].no_data_state == "Alerting"
    error_message = "a check that stopped publishing has stopped being monitored, which must not be silent"
  }
}

run "notification_is_routed_per_rule" {
  command = plan

  assert {
    condition     = grafana_rule_group.down.rule[0].notification_settings[0].contact_point == grafana_contact_point.operators.name
    error_message = "the rule names its own contact point, leaving the stack's notification policy alone"
  }

  assert {
    condition     = one(grafana_contact_point.operators.email[*].addresses[0]) == "ops@example.com"
    error_message = "alerts go to the configured addresses"
  }
}

run "an_unaddressed_alert_fails_the_plan" {
  command = plan

  variables {
    email_addresses = []
  }

  expect_failures = [terraform_data.alerting_is_addressed]
}

run "alerting_without_checks_fails_the_plan" {
  command = plan

  variables {
    jobs = []
  }

  expect_failures = [terraform_data.alerting_is_addressed]
}
