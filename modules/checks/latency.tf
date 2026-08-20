# A latency budget only means anything in the band between itself and the
# probe's own timeout. An execution that runs past timeout_seconds reports
# failure, so a budget at or above the timeout can never be exceeded while
# the check is up, and the amber "slow" state it configures is unreachable.
# Silent when it happens, which is why the plan refuses it.
locals {
  unreachable_latency_budgets = [
    for k, c in var.checks :
    "${k} (budget ${c.latency_budget_ms}ms, timeout ${local.timeout_ms[k]}ms)"
    if c.latency_budget_ms != null && c.latency_budget_ms >= local.timeout_ms[k]
  ]
}

resource "terraform_data" "latency_budgets_are_reachable" {
  input = local.unreachable_latency_budgets

  lifecycle {
    precondition {
      condition = length(local.unreachable_latency_budgets) == 0
      error_message = join("\n", [
        "latency_budget_ms is at or above the probe's timeout, so these checks can only ever read up or down, never slow:",
        join(", ", local.unreachable_latency_budgets),
        "Lower latency_budget_ms, or raise timeout_seconds.",
      ])
    }
  }
}
