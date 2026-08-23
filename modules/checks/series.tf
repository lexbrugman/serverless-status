# How much of the account's metrics allowance the checks are using.
#
# Reported, not enforced. The count follows from what Synthetic Monitoring
# publishes per check per probe location — histograms and summaries, mostly
# — which Grafana documents nowhere and does not contract to hold steady,
# so there is nothing here a plan could hold anyone to.
#
# It cannot be asserted either, even softly. The reads authenticate with a
# service account this module creates, so on the apply that first builds an
# account they are deferred and any condition over them is unknowable until
# afterwards — which OpenTofu treats as an error, not a warning.
#
# The enforced ceiling is published, unlike anything about executions — but
# on the org-level grafanacloud-usage datasource rather than on the SM
# tenant, so it is read through the stack's own Grafana rather than the SM
# API. What is not published, for either resource, is the allowance a
# subscription includes: the number that starts costing money sits below
# the number that starts rejecting writes, and only the second is readable. Two
# reads: the datasource's uid, then one query for both numbers. Neither is
# a new dependency — the providers cannot plan this module at all without
# the same stack's APIs answering.
data "http" "usage_datasource" {
  url = "${data.grafana_cloud_stack.this.url}/api/datasources/name/grafanacloud-usage"

  request_headers = {
    Authorization = "Bearer ${grafana_cloud_stack_service_account_token.alerting.key}"
  }

  retry {
    attempts = 2
  }
}

data "http" "series" {
  url = format(
    "%s/api/datasources/proxy/uid/%s/api/v1/query?query=%s",
    data.grafana_cloud_stack.this.url,
    local.usage_datasource_uid,
    urlencode(join("", [
      "grafanacloud_instance_active_series{stack_id=\"${data.grafana_cloud_stack.this.id}\"}",
      " or grafanacloud_instance_metrics_limits{",
      "limit_name=\"${local.series_ceiling_metric}\",",
      "stack_id=\"${data.grafana_cloud_stack.this.id}\"}",
    ])),
  )

  request_headers = {
    Authorization = "Bearer ${grafana_cloud_stack_service_account_token.alerting.key}"
  }

  retry {
    attempts = 2
  }
}

output "metrics_series" {
  description = "What this account's checks are costing its metrics allowance: series in use, and the ceiling Grafana enforces before it starts rejecting writes. That ceiling is not the allowance a subscription includes, and is higher — 15k enforced against 10k included on the free tier — so crossing the included figure costs money long before this number is reached. The included figure is published nowhere, which is the same gap monthly_execution_budget exists to fill. Reported rather than asserted: the count follows from what Synthetic Monitoring emits per check per probe location, which Grafana documents nowhere and does not contract to hold steady, so there is nothing here a plan could enforce. Zeroes mean the reading failed rather than that there is room."
  value = {
    used = local.series_used
    # Not "limit": this is where writes start being rejected, which is
    # above where the subscription starts being exceeded.
    enforced_ceiling = local.series_ceiling
  }
}
