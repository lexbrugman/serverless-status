#!/usr/bin/env bash
# Posts the plan as the PR's single, always-current review comment.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${PR_NUMBER:?}"

{
  echo '### tofu plan'
  echo '```'
  tail -c 60000 plan.txt
  echo '```'
} >comment.md
gh pr comment "$PR_NUMBER" --body-file comment.md --create-if-none --edit-last
