#!/usr/bin/env bash
# Applies everything and writes the handover — the values that switch
# routine CI on — to the run summary.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu apply -input=false -auto-approve
{
  echo "## Bootstrap complete — finish the handover"
  echo
  echo "- repository variable \`PLAN_ROLE_ARN\`: \`$(tofu output -raw plan_role_arn)\`"
  echo "- restrict the \`production\` environment's deployment branches to master"
  echo "- verify the page and certificate at: \`$(tofu output -raw distribution_domain)\`"
} >>"$GITHUB_STEP_SUMMARY"
