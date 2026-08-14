# The free-tier execution budget is an invariant, not a drift signal, so it
# is a precondition that hard-fails the plan — a `check` block would let an
# over-budget configuration sail past with a yellow warning.
locals {
  # 43200 = minutes per 30-day month, times one execution per probe location.
  executions_per_check = { for k, c in var.checks :
    k => ceil(43200 / coalesce(c.frequency_minutes, local.freq_default[c.type])) * length(var.probe_locations)
  }
  monthly_executions = length(var.checks) == 0 ? 0 : sum(values(local.executions_per_check))

  execution_ranking = reverse(sort([for k, n in local.executions_per_check : format("%010d|%s", n, k)]))
  largest_consumers = [for entry in slice(local.execution_ranking, 0, min(3, length(local.execution_ranking))) :
    "${split("|", entry)[1]} (${tonumber(split("|", entry)[0])})"
  ]
}

resource "terraform_data" "execution_budget" {
  input = local.monthly_executions

  lifecycle {
    precondition {
      condition = local.monthly_executions <= var.monthly_execution_budget
      error_message = join("\n", [
        "monthly Synthetic Monitoring executions: ${local.monthly_executions} — exceeds budget of ${var.monthly_execution_budget} (Grafana Cloud free tier: 100000).",
        "Largest consumers: ${join(", ", local.largest_consumers)}.",
        "Raise frequency_minutes, drop a probe location, or raise monthly_execution_budget.",
      ])
    }
  }
}
