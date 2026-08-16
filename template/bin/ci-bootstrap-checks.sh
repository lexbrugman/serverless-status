#!/usr/bin/env bash
# Applies only the Grafana checks — one target per org file — so step zero
# can verify them before anything downstream exists.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu init -input=false -backend-config=state.tfbackend
targets=()
for file in grafana_org_*.tf; do
  org="${file#grafana_org_}"
  targets+=("-target=module.checks_${org%.tf}")
done
tofu apply -input=false -auto-approve "${targets[@]}"
