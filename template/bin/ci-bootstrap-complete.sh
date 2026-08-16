#!/usr/bin/env bash
# Marks the bootstrap done — the marker is what switches routine CI on —
# and writes what is left to do by hand.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${PUSH_BRANCH:?}" "${GITHUB_STEP_SUMMARY:?}"

cat >.bootstrap-complete <<'EOF'
The bootstrap completed. This file switches routine CI on: plan, apply,
and drift stay inert while it is absent, so pushes during a bootstrap
cannot race it. Deleting it re-arms the bootstrap.
EOF

if [[ -n "$(git status --porcelain .bootstrap-complete)" ]]; then
  git config user.name 'github-actions[bot]'
  git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
  git add .bootstrap-complete
  git commit -m "Complete the bootstrap"
  git push origin "HEAD:${PUSH_BRANCH}"
fi

{
  echo "## Bootstrap complete"
  echo
  echo "Routine CI is on: pull requests get a plan comment, master pushes apply."
  echo
  echo "Two things are still yours to do:"
  echo "- restrict the \`production\` environment's deployment branches to master —"
  echo "  the apply role's trust accepts only that environment, and the restriction"
  echo "  is what makes it mean master"
  echo "- verify the page and its certificate at \`$(tofu -chdir=tofu output -raw distribution_domain)\`"
  echo "  before pointing DNS at it"
} >>"$GITHUB_STEP_SUMMARY"
