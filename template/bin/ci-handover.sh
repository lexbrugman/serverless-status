#!/usr/bin/env bash
# Hand CI the wheel: push everything the workflows expect into GitHub —
# the two secrets, the two role ARNs, and the production environment the
# apply job runs in. Requires an authenticated gh, the two TF_VAR secrets
# still exported, and a completed first apply (the role ARNs are outputs).
#
# Secrets land at repository level on purpose: the plan and drift jobs run
# outside any environment, so environment secrets would never reach them.
# The production environment exists to gate the apply job; its protection
# rules are a console decision.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${TF_VAR_grafana_cloud_tokens:?TF_VAR_grafana_cloud_tokens must be exported}"
: "${TF_VAR_state_passphrase:?TF_VAR_state_passphrase must be exported}"

if ! command -v gh >/dev/null; then
  echo "ERROR: gh not found — set the values by hand, see the setup guide." >&2
  exit 1
fi

plan_role_arn="$(tofu output -raw plan_role_arn)"
apply_role_arn="$(tofu output -raw apply_role_arn)"

gh api -X PUT "repos/{owner}/{repo}/environments/production" >/dev/null
gh secret set GRAFANA_CLOUD_TOKENS --body "$TF_VAR_grafana_cloud_tokens"
gh secret set STATE_PASSPHRASE --body "$TF_VAR_state_passphrase"
gh variable set PLAN_ROLE_ARN --body "$plan_role_arn"
gh variable set APPLY_ROLE_ARN --body "$apply_role_arn"

cat <<EOF
CI configured:
  repository secrets   GRAFANA_CLOUD_TOKENS, STATE_PASSPHRASE
  repository variables PLAN_ROLE_ARN=$plan_role_arn
                       APPLY_ROLE_ARN=$apply_role_arn
  environment          production (add protection rules in the console)
EOF
