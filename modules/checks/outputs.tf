locals {
  # Groups ordered by their lowest member order, then name.
  group_min_order = { for g in distinct([for c in values(var.checks) : c.group]) :
    g => min([for c in values(var.checks) : c.order if c.group == g]...)
  }
  groups_ordered = [for entry in sort([for g, o in local.group_min_order : format("%010d|%s", o, g)]) :
    split("|", entry)[1]
  ]
}

output "page_manifest" {
  description = "Everything the renderer needs to know about the checks and the page — the seam between the two modules. schema_version exists so a half-merged ref bump fails at plan time, not as a baffling runtime error."
  value = {
    schema_version = 1
    site           = var.site
    page           = var.page
    checks = { for k, c in var.checks : k => {
      display           = c.display
      group             = c.group
      type              = c.type
      host              = c.host
      port              = c.type == "ping" ? null : coalesce(c.port, local.port_default[c.type])
      path              = contains(["https", "http"], c.type) ? coalesce(c.path, "/") : null
      order             = c.order
      latency_budget_ms = c.latency_budget_ms
    } }
    groups = local.groups_ordered
  }
}

output "prometheus" {
  description = "Prometheus query endpoint and credentials for the renderer, stored in SSM by the renderer module — never in GitHub, a file, or a shell."
  sensitive   = true
  value = {
    query_url = "${data.grafana_cloud_stack.this.prometheus_url}/api/prom"
    user      = tostring(data.grafana_cloud_stack.this.prometheus_user_id)
    token     = grafana_cloud_access_policy_token.metrics_read.token
  }
}

output "monthly_executions" {
  description = "Computed Synthetic Monitoring executions per month, for eyeballing against the Grafana console's own accounting."
  value       = local.monthly_executions
}
