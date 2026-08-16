#!/usr/bin/env bash
# Rebuilds the instance from the pinned release and pushes the result, so
# the tree CI plans and applies is always the generated one — a ref bump
# or an orgs-map change lands as a sync commit on the branch. Safe against
# self-replacement: the rebuild recreates this file rather than writing
# into it, so the running copy is undisturbed.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${PUSH_BRANCH:?}"

bin/sync.sh
if [[ -z "$(git status --porcelain)" ]]; then
  echo "Instance already matches the pinned release."
  exit 0
fi

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
ref="$(sed -n 's/.*?ref=\([^"]*\)".*/\1/p' tofu/page.tf | head -n 1)"
git commit -m "Sync instance to ${ref}"
# GITHUB_TOKEN may not write .github/workflows; a release that changes
# those needs bin/sync.sh run locally (git, sed, and awk only) on this
# branch.
git push origin "HEAD:${PUSH_BRANCH}" || {
  echo "::error::Push refused — the release likely changed workflow files." \
    "Run bin/sync.sh locally on this branch and push."
  exit 1
}
