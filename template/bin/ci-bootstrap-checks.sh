#!/usr/bin/env bash
# Step zero: applies only the Grafana checks — one target per org file —
# and writes the manual verification checklist to the run summary.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

targets=()
for file in org_*.tf; do
  org="${file#org_}"
  targets+=("-target=module.checks_${org%.tf}")
done
tofu apply -input=false -auto-approve "${targets[@]}"
{
  echo "## Step zero applied"
  echo
  echo "Verify in the Grafana console before going further:"
  echo "- \`probe_success\` reports 1 for the smtp checks (port-25 egress works)"
  echo "- the TCP dialogue steps read greeting, EHLO, STARTTLS, upgrade, EHLO, QUIT — in that order"
  echo
  echo "Then dispatch this workflow again with phase: **all**."
} >>"$GITHUB_STEP_SUMMARY"
