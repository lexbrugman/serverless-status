#!/usr/bin/env bash
# Export the region this instance runs in, read from the file that states
# it. A workflow carrying its own copy is a second answer to a question
# the instance already answered, and the two disagree silently: the
# providers take the file's value while the credentials take the copy.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${GITHUB_ENV:?}"

region="$(sed -n 's/^[[:space:]]*region[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' state.tfbackend | head -n 1)"
if [[ -z "$region" ]]; then
  echo "ERROR: no region in state.tfbackend — it states where this instance runs." >&2
  exit 1
fi

echo "AWS_REGION=${region}" >>"$GITHUB_ENV"
echo "region: ${region}"
