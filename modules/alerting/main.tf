# Notification, provisioned here and executed by Grafana. The alert fires
# from the layer that observed the failure: nothing of this stack's own —
# not the Lambda, not CloudFront, not the page — sits between a failing
# probe and the message, so an outage that takes the renderer down still
# reaches a human.

locals {
  # One rule, one alert instance per job: Grafana's alerting is
  # multi-dimensional, so a rule per check would be N copies of one idea.
  job_pattern = "^(${join("|", var.jobs)})$"

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

  rule {
    name      = "Check down"
    condition = local.threshold_ref
    for       = "${var.down_for_minutes}m"

    # Silence is a failure too: a check that stops publishing has stopped
    # being monitored, which is exactly what nobody notices on their own.
    no_data_state  = "Alerting"
    exec_err_state = "Alerting"

    data {
      ref_id         = local.query_ref
      datasource_uid = grafana_data_source.metrics.uid

      relative_time_range {
        from = 600
        to   = 0
      }

      model = jsonencode({
        refId      = local.query_ref
        editorMode = "code"
        expr       = "min by (job) (probe_success{job=~\"${local.job_pattern}\"})"
        instant    = true
        range      = false
      })
    }

    data {
      ref_id         = local.threshold_ref
      datasource_uid = "__expr__"

      relative_time_range {
        from = 600
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
      summary = "{{ $labels.job }} has been failing for ${var.down_for_minutes}m."
    }

    # Routed per rule, so the stack's own notification policy tree is left
    # exactly as its owner arranged it.
    notification_settings {
      contact_point = grafana_contact_point.operators.name
      group_by      = ["alertname", "job"]
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
