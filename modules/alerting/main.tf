# Notification, provisioned here and executed by Grafana. The alert fires
# from the layer that observed the failure: nothing of this stack's own —
# not the Lambda, not CloudFront, not the page — sits between a failing
# probe and the message, so an outage that takes the renderer down still
# reaches a human.

locals {
  # One rule, one alert instance per job: Grafana's alerting is
  # multi-dimensional, so a rule per check would be N copies of one idea.
  job_keys    = sort([for job in var.jobs : job.key])
  job_pattern = "^(${join("|", local.job_keys)})$"

  # One rule per probe interval. The window that turns samples into a
  # verdict is a multiple of that interval, so checks running at different
  # rates cannot share one without the slower being judged on fewer
  # samples than the faster.
  by_frequency = { for job in var.jobs : tostring(job.frequency_minutes) => job.key... }

  # One late probe is tolerated; below that there is not enough in the
  # window to judge. Mirrors prometheus.up_query in the renderer — the two
  # are pinned to the same literal by tests on both sides.
  min_samples = max(1, var.down_window_multiple - 1)

  selectors = { for frequency, keys in local.by_frequency :
    frequency => "probe_success{job=~\"^(${join("|", sort(keys))})$\"}"
  }

  windows = { for frequency, keys in local.by_frequency :
    frequency => tonumber(frequency) * var.down_window_multiple
  }

  up_expr = { for frequency, keys in local.by_frequency : frequency => join("", [
    "(sum by (job) (sum_over_time(${local.selectors[frequency]}[${local.windows[frequency]}m]))",
    " / sum by (job) (count_over_time(${local.selectors[frequency]}[${local.windows[frequency]}m]))",
    " >= bool ${var.down_quorum}) and ",
    "(sum by (job) (count_over_time(${local.selectors[frequency]}[${local.windows[frequency]}m])) >= ${local.min_samples})",
  ]) }

  query_ref     = "probe"
  threshold_ref = "failing"

  # Ten minutes without a render is unambiguous against a one-minute
  # schedule, and short enough that a dead renderer is a morning problem
  # rather than a weekly one.
  heartbeat_stale_seconds = 600

  # Long enough that the slowest check's own interval cannot look like
  # silence, short enough to matter the same day.
  unreported_for = "30m"
}

# Emptiness is caught here rather than on the variables: a disabled module
# is still validated, and a rule that matches nothing or announces to
# nobody is a mistake worth a plan-time error when it is real.
resource "terraform_data" "alerting_is_addressed" {
  input = var.jobs

  lifecycle {
    precondition {
      condition     = length(var.jobs) > 0
      error_message = "alerting needs at least one check to watch."
    }

    precondition {
      condition     = length(var.email_addresses) > 0
      error_message = "an alert with no recipient is not an alert; give alerting.email_addresses at least one address."
    }
  }
}

# The stack ships a Prometheus datasource of its own, but its name is a
# convention rather than a contract. This one is created from the same
# read credentials the renderer uses, so the rules below point at an
# address this configuration knows rather than one it guessed.
resource "grafana_data_source" "metrics" {
  provider = grafana.stack

  type                = "prometheus"
  name                = "serverless-status"
  url                 = var.prometheus.query_url
  basic_auth_enabled  = true
  basic_auth_username = var.prometheus.user

  secure_json_data_encoded = jsonencode({
    basicAuthPassword = var.prometheus.token
  })
}

resource "grafana_folder" "alerts" {
  provider = grafana.stack

  title = "serverless-status"
}

resource "grafana_contact_point" "operators" {
  provider = grafana.stack

  name = "serverless-status"

  email {
    addresses = var.email_addresses
    subject   = "{{ .CommonLabels.job }} is down"
  }
}

resource "grafana_rule_group" "down" {
  provider = grafana.stack

  name             = "serverless-status"
  folder_uid       = grafana_folder.alerts.uid
  interval_seconds = 60

  dynamic "rule" {
    for_each = local.up_expr

    content {
      name = "Check down (every ${rule.key}m)"
      # The debounce lives in the query, counted in probe executions, so
      # there is nothing left for a pending period to add.
      condition = local.threshold_ref
      for       = "0s"

      # Silence is the other rule's job; alerting on it here would page
      # once per frequency group as well.
      no_data_state  = "OK"
      exec_err_state = "Alerting"

      data {
        ref_id         = local.query_ref
        datasource_uid = grafana_data_source.metrics.uid

        relative_time_range {
          from = 3600
          to   = 0
        }

        model = jsonencode({
          refId      = local.query_ref
          editorMode = "code"
          expr       = rule.value
          instant    = true
          range      = false
        })
      }

      data {
        ref_id         = local.threshold_ref
        datasource_uid = "__expr__"

        relative_time_range {
          from = 3600
          to   = 0
        }

        model = jsonencode({
          refId      = local.threshold_ref
          type       = "threshold"
          expression = local.query_ref
          datasource = { type = "__expr__", uid = "__expr__" }
          conditions = [{
            evaluator = { type = "lt", params = [1] }
            operator  = { type = "and" }
            query     = { params = [local.query_ref] }
            reducer   = { type = "last", params = [] }
            type      = "query"
          }]
        })
      }

      labels = {
        source = "serverless-status"
      }

      annotations = {
        summary = "{{ $labels.job }} is down: fewer than ${var.down_quorum} of its probe executions succeeded over the last ${var.down_window_multiple} intervals."
      }

      # Routed per rule, so the stack's own notification policy tree is
      # left exactly as its owner arranged it.
      notification_settings {
        contact_point = grafana_contact_point.operators.name
        group_by      = ["alertname", "job"]
      }
    }
  }

  # The renderer publishes the moment of its last successful run. Nothing
  # else watches it: a page that stops updating serves its last render
  # perfectly, and only a viewer's own clock would ever notice.
  rule {
    name      = "Status page not rendering"
    condition = local.threshold_ref
    for       = "5m"

    # No heartbeat at all is the failure this rule exists for.
    no_data_state  = "Alerting"
    exec_err_state = "Alerting"

    data {
      ref_id         = local.query_ref
      datasource_uid = grafana_data_source.metrics.uid

      relative_time_range {
        from = 3600
        to   = 0
      }

      model = jsonencode({
        refId      = local.query_ref
        editorMode = "code"
        expr       = "time() - max(status_page_rendered_timestamp)"
        instant    = true
        range      = false
      })
    }

    data {
      ref_id         = local.threshold_ref
      datasource_uid = "__expr__"

      relative_time_range {
        from = 3600
        to   = 0
      }

      model = jsonencode({
        refId      = local.threshold_ref
        type       = "threshold"
        expression = local.query_ref
        datasource = { type = "__expr__", uid = "__expr__" }
        conditions = [{
          evaluator = { type = "gt", params = [local.heartbeat_stale_seconds] }
          operator  = { type = "and" }
          query     = { params = [local.query_ref] }
          reducer   = { type = "last", params = [] }
          type      = "query"
        }]
      })
    }

    labels = {
      source = "serverless-status"
    }

    annotations = {
      summary = "The status page has not rendered for over ${local.heartbeat_stale_seconds}s."
    }

    notification_settings {
      contact_point = grafana_contact_point.operators.name
      group_by      = ["alertname"]
    }
  }

  # A check that stops publishing is invisible to any query this stack can
  # run against itself: absence carries no labels, so nothing here knows
  # which check went missing. The renderer does — it holds the configured
  # set — so it reports presence, and this watches that.
  rule {
    name      = "Check not reporting"
    condition = local.threshold_ref
    for       = local.unreported_for

    # Silence here means the renderer is gone, which the heartbeat rule
    # already owns. Alerting on it too would page once per check.
    no_data_state  = "OK"
    exec_err_state = "Alerting"

    data {
      ref_id         = local.query_ref
      datasource_uid = grafana_data_source.metrics.uid

      relative_time_range {
        from = 3600
        to   = 0
      }

      model = jsonencode({
        refId      = local.query_ref
        editorMode = "code"
        expr       = "min by (job) (status_page_check_observed{job=~\"${local.job_pattern}\"})"
        instant    = true
        range      = false
      })
    }

    data {
      ref_id         = local.threshold_ref
      datasource_uid = "__expr__"

      relative_time_range {
        from = 3600
        to   = 0
      }

      model = jsonencode({
        refId      = local.threshold_ref
        type       = "threshold"
        expression = local.query_ref
        datasource = { type = "__expr__", uid = "__expr__" }
        conditions = [{
          evaluator = { type = "lt", params = [1] }
          operator  = { type = "and" }
          query     = { params = [local.query_ref] }
          reducer   = { type = "last", params = [] }
          type      = "query"
        }]
      })
    }

    labels = {
      source = "serverless-status"
    }

    annotations = {
      summary = "{{ $labels.job }} has stopped reporting — it is no longer being monitored."
    }

    notification_settings {
      contact_point = grafana_contact_point.operators.name
      group_by      = ["alertname", "job"]
    }
  }
}
