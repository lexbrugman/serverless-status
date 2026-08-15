#!/usr/bin/env bash
# Hand CI the wheel: print every name and value the workflows expect, ready
# to paste into GitHub. Requires the two TF_VAR secrets still exported and
# a completed first apply (the role ARNs are outputs).
#
# Secrets belong at repository level: the plan and drift jobs run outside
# any environment, so environment secrets would never reach them. The
# production environment needs no creating — GitHub creates it when the
# first apply job references it; protecting it is the part that is yours.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${TF_VAR_grafana_cloud_tokens:?TF_VAR_grafana_cloud_tokens must be exported}"
: "${TF_VAR_state_passphrase:?TF_VAR_state_passphrase must be exported}"

tofu_bin="$(command -v tofu || true)"
if [[ -z "$tofu_bin" ]]; then
  tofu_bin="$ROOT/bin/tofu.sh"
fi

plan_role_arn="$("$tofu_bin" output -raw plan_role_arn)"
apply_role_arn="$("$tofu_bin" output -raw apply_role_arn)"

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

The "production" environment appears on the first master push (GitHub
creates it when the apply job references it). Then, under Settings ->
Environments, restrict its deployment branches to master — the apply
role's trust accepts any run bound to this environment, and the branch
restriction is what makes that mean master only. Add reviewers if you
want a human gate too.
EOF
