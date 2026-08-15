#!/usr/bin/env bash
# Hand CI the wheel: print every name and value the workflows expect, ready
# to paste into GitHub. Requires the two TF_VAR secrets still exported and
# a completed first apply (the role ARNs are outputs).
#
# Secrets belong at repository level: the plan and drift jobs run outside
# any environment, so environment secrets would never reach them. The
# production environment exists to gate the apply job; its protection
# rules are a console decision.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${TF_VAR_grafana_cloud_tokens:?TF_VAR_grafana_cloud_tokens must be exported}"
: "${TF_VAR_state_passphrase:?TF_VAR_state_passphrase must be exported}"

plan_role_arn="$(tofu output -raw plan_role_arn)"
apply_role_arn="$(tofu output -raw apply_role_arn)"

cat <<EOF
Set in GitHub, under Settings -> Secrets and variables -> Actions:

Repository secrets:
  GRAFANA_CLOUD_TOKENS
$TF_VAR_grafana_cloud_tokens

  STATE_PASSPHRASE
$TF_VAR_state_passphrase

Repository variables:
  PLAN_ROLE_ARN
$plan_role_arn

  APPLY_ROLE_ARN
$apply_role_arn

Then, under Settings -> Environments: create "production" and add the
protection rules you want — it gates the apply job.
EOF
