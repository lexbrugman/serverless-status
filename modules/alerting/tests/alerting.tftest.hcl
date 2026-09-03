# What the rule asks Prometheus and where the answer goes — offline, via
# mocked providers. Delivery itself is not assertable here: that a message
# reaches a mailbox is Grafana's to do and a human's to confirm.

mock_provider "grafana" {
  alias = "stack"
}

variables {
  down_jobs = [
    { key = "api-example-com-https", frequency_minutes = 5 },
    { key = "mx1-example-com-smtp", frequency_minutes = 5 },
  ]
  # One more than the down list: gw-example-com-ping said alert: false.
  reporting_jobs = [
    { key = "api-example-com-https", display = "API", target = "api.example.com/health", frequency_minutes = 5 },
    { key = "mx1-example-com-smtp", display = "Inbound mail", target = "mx1.example.com", frequency_minutes = 5 },
    { key = "gw-example-com-ping", display = "Uplink", target = "gw.example.com", frequency_minutes = 10 },
  ]
  page_url             = "https://status.example.com"
  email_addresses      = ["ops@example.com"]
  down_window_multiple = 3
  down_quorum          = 0.5

  prometheus = {
    query_url = "https://prometheus-prod-01-eu-west-0.grafana.net/api/prom"
    user      = "987654"
    token     = "mock-read-token"
  }
}

run "the_rule_watches_every_alerting_check" {
  command = plan

  # Pinned against prometheus.up_query in the renderer, which builds the
  # identical string. The page and the pager answer to one definition of
  # down or they will eventually tell different stories.
  assert {
    condition = jsondecode(grafana_rule_group.down.rule[0].data[0].model).expr == join("", [
      "(sum by (job) (sum_over_time(probe_success{job=~\"^(api-example-com-https|mx1-example-com-smtp)$\"}[15m]))",
      " / sum by (job) (count_over_time(probe_success{job=~\"^(api-example-com-https|mx1-example-com-smtp)$\"}[15m]))",
      " >= bool 0.5) and ",
      "(sum by (job) (count_over_time(probe_success{job=~\"^(api-example-com-https|mx1-example-com-smtp)$\"}[15m])) >= 2)",
    ])
    error_message = "the alert rule and the renderer must ask Prometheus the same question"
  }

  assert {
    condition     = jsondecode(grafana_rule_group.down.rule[0].data[0].model).instant == true
    error_message = "the current value decides, not an average over a window"
  }
}

run "it_fires_only_after_the_configured_wait" {
  command = plan

  # The debounce is counted in probe executions inside the query, so there
  # is nothing left for a pending period to add. A wall-clock `for` shorter
  # than the probe interval only delays: it re-reads one sample and never
  # requires a second failure.
  assert {
    condition     = grafana_rule_group.down.rule[0].for == "0s"
    error_message = "the wait is a count of executions in the query, not a pending period"
  }

  assert {
    condition = (
      jsondecode(grafana_rule_group.down.rule[0].data[1].model).conditions[0].evaluator.type == "lt" &&
      tonumber(jsondecode(grafana_rule_group.down.rule[0].data[1].model).conditions[0].evaluator.params[0]) == 1
    )
    error_message = "the alert condition is probe_success below 1"
  }

  # Silence is a different failure from failure, and it has its own rule.
  # Alerting on no-data here as well would page once per frequency group
  # every time the renderer stopped reporting.
  assert {
    condition     = grafana_rule_group.down.rule[0].no_data_state == "OK"
    error_message = "no-data belongs to the not-reporting rule, not to this one"
  }
}

run "silence_and_a_dead_renderer_each_have_their_own_rule" {
  command = plan

  assert {
    condition = [for rule in grafana_rule_group.down.rule : rule.name] == [
      "Check down (every 5m)",
      "Status page not rendering",
      "Check not reporting",
    ]
    error_message = "one down rule per probe interval, plus the two failures a down rule cannot see"
  }

  # A check that stops publishing produces no series at all, so nothing
  # Grafana can ask about probe_success will name it. The renderer holds
  # the configured set and reports presence; this is what watches that.
  assert {
    condition = strcontains(
      jsondecode(grafana_rule_group.down.rule[2].data[0].model).expr,
      "status_page_check_observed"
    )
    error_message = "silence is detected from what the renderer reports, not from what is missing"
  }

  assert {
    condition     = grafana_rule_group.down.rule[2].no_data_state == "OK"
    error_message = "a dead renderer is the heartbeat rule's to report, once, not once per check"
  }

  assert {
    condition     = grafana_rule_group.down.rule[1].no_data_state == "Alerting"
    error_message = "no heartbeat at all is exactly the failure the heartbeat rule exists for"
  }
}

# A check reports as unobserved until it has a verdict's worth of samples,
# which is its own interval times the window. A wait shorter than that pages
# for a check that is merely new, and how long "merely new" lasts is a fact
# about the check rather than a number to pick.
run "the_silence_wait_follows_the_slowest_check" {
  command = plan

  assert {
    condition     = grafana_rule_group.down.rule[2].for == "30m"
    error_message = "the wait must be the slowest reporting check's interval times the window"
  }
}

run "a_slower_check_widens_the_silence_wait" {
  command = plan

  variables {
    reporting_jobs = [
      { key = "api-example-com-https", display = "API", target = "api.example.com/health", frequency_minutes = 5 },
      { key = "quarterly-example-com-https", display = "Batch", target = "batch.example.com", frequency_minutes = 60 },
    ]
  }

  assert {
    condition     = grafana_rule_group.down.rule[2].for == "180m"
    error_message = "a check that reports hourly must not be paged about after thirty minutes"
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

run "alerting_watching_nothing_fails_the_plan" {
  command = plan

  variables {
    reporting_jobs = []
  }

  expect_failures = [var.reporting_jobs]
}

run "opting_out_of_paging_does_not_opt_out_of_being_watched" {
  command = plan

  # alert: false says a failure of the thing is not worth a page. It does
  # not say a failure of the monitoring is, and a check nobody is running
  # is the second.
  assert {
    condition = !strcontains(
      jsondecode(grafana_rule_group.down.rule[0].data[0].model).expr,
      "gw-example-com-ping"
    )
    error_message = "a check that opted out must not be paged about when it fails"
  }

  assert {
    condition = strcontains(
      jsondecode(grafana_rule_group.down.rule[2].data[0].model).expr,
      "gw-example-com-ping"
    )
    error_message = "every check is watched for going quiet, opted out or not"
  }
}

run "the_notification_names_the_check_and_points_at_the_record" {
  command = plan

  assert {
    condition     = strcontains(one(grafana_contact_point.operators.email[*].subject), "{{ if eq .Status \"resolved\" }}Recovered: {{ end }}")
    error_message = "a recovery announcing itself as an outage is read as a second one"
  }

  assert {
    condition     = strcontains(one(grafana_contact_point.operators.email[*].subject), "{{ if eq .CommonLabels.job \"api-example-com-https\" }}API (api.example.com/health){{ end }}")
    error_message = "the subject must name the check, not the job slug Grafana happens to know it by"
  }

  assert {
    condition     = strcontains(one(grafana_contact_point.operators.email[*].message), var.page_url)
    error_message = "the notification must point at the record it cannot restate"
  }

  assert {
    condition     = !strcontains(lower(one(grafana_contact_point.operators.email[*].message)), "duration")
    error_message = "Grafana times its own window, not the outage; a duration here would contradict the log"
  }

  assert {
    condition     = strcontains(grafana_rule_group.down.rule[0].annotations["summary"], "is not responding")
    error_message = "the summary states what happened before how it was decided"
  }

  assert {
    condition     = strcontains(grafana_rule_group.down.rule[0].annotations["summary"], "{{ if eq $labels.job \"mx1-example-com-smtp\" }}Inbound mail (mx1.example.com){{ end }}")
    error_message = "the summary must name the check that failed"
  }
}
