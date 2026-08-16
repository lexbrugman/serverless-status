output "check_manifest" {
  description = "This stack's checks, resolved, for the renderer — the seam between the modules. A page can merge several stacks' manifests, one per Grafana account. schema_version exists so a half-merged ref bump fails at plan time, not as a baffling runtime error."
  value = {
    schema_version = 2
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

output "stack" {
  description = "How to reach this stack's own API: the URL and a service account token. Feeds the root's per-account grafana provider, which the alerting module runs against."
  sensitive   = true
  value = {
    url  = data.grafana_cloud_stack.this.url
    auth = grafana_cloud_stack_service_account_token.alerting.key
  }
}
