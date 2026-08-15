#!/usr/bin/env bash
# Imports the console-created OIDC provider and apply role into state, so
# their trust is managed from the first apply on and console-wizard
# sloppiness converges to the written policy. Already-imported resources
# are left alone; reruns skip.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu init -input=false -backend-config=state.tfbackend
account_id="$(aws sts get-caller-identity --query Account --output text)"
state="$(tofu state list 2>/dev/null || true)"
# An import evaluates the whole configuration; the sm provider configs
# are only evaluable once the installations from phase checks are in
# state.
if ! grep -q 'grafana_synthetic_monitoring_installation' <<<"$state"; then
  echo "ERROR: no Synthetic Monitoring installation in state — dispatch phase checks first." >&2
  exit 1
fi
if ! grep -q 'module.ci.aws_iam_openid_connect_provider.github' <<<"$state"; then
  tofu import -input=false 'module.ci.aws_iam_openid_connect_provider.github' \
    "arn:aws:iam::${account_id}:oidc-provider/token.actions.githubusercontent.com"
fi
if ! grep -q 'module.ci.aws_iam_role.apply$' <<<"$state"; then
  tofu import -input=false 'module.ci.aws_iam_role.apply' serverless-status-apply
fi
