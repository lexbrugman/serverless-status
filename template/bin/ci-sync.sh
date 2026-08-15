#!/usr/bin/env bash
# Rebuilds the instance when a PR bumps the pinned release ref, committing
# the result back to the PR branch so the plan — and the merge — carry the
# synced tree. Safe against self-replacement: the rebuild recreates this
# file rather than writing into it, so the running copy is undisturbed.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${BASE_BRANCH:?}" "${HEAD_BRANCH:?}"

extract_ref() { sed -n 's/.*?ref=\([^"]*\)".*/\1/p' | head -n 1; }

git fetch --quiet --depth 1 origin "$BASE_BRANCH"
base_ref="$(git show "origin/${BASE_BRANCH}:page.tf" | extract_ref)"
head_ref="$(extract_ref <page.tf)"
if [[ "$base_ref" == "$head_ref" ]]; then
  echo "Pinned release unchanged (${head_ref}); nothing to sync."
  exit 0
fi

bin/sync.sh "$head_ref"
if [[ -z "$(git status --porcelain)" ]]; then
  echo "Instance already matches release ${head_ref}."
  exit 0
fi

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m "Sync instance to ${head_ref}"
# GITHUB_TOKEN may not write .github/workflows; a release that changes
# those needs bin/sync.sh run locally (git and sed only) on this branch.
git push origin "HEAD:${HEAD_BRANCH}" || {
  echo "::error::Push refused — the release likely changed workflow files." \
    "Run bin/sync.sh locally on this branch and push."
  exit 1
}
