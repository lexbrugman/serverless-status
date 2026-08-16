#!/usr/bin/env bash
# Whether routine CI may run, and the role it plans with. Both are derived,
# never configured: the marker is written by the bootstrap's final step, and
# the plan role's name is fixed by the CI wiring, so the apply role's ARN —
# the one value the setup states by hand — locates it.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${APPLY_ROLE_ARN:?}" "${GITHUB_OUTPUT:?}"

apply_role_name="serverless-status-apply"
plan_role_name="serverless-status-plan"

if [[ "$APPLY_ROLE_ARN" != *"/${apply_role_name}" ]]; then
  echo "ERROR: APPLY_ROLE_ARN must name the role ${apply_role_name}; got ${APPLY_ROLE_ARN}." >&2
  exit 1
fi

if [[ -f .bootstrap-complete ]]; then
  bootstrapped=true
else
  bootstrapped=false
  echo "Bootstrap has not completed; plan, apply, and drift stay inert."
fi

{
  echo "bootstrapped=${bootstrapped}"
  echo "plan_role_arn=${APPLY_ROLE_ARN%/*}/${plan_role_name}"
} >>"$GITHUB_OUTPUT"
