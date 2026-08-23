#!/usr/bin/env bash
# Creates the state bucket and commits the bootstrap root's state back
# (bucket metadata only, no secrets). The committed state file is the
# done-marker: reruns skip.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${PUSH_BRANCH:?}"

if [[ -f tofu/bootstrap/terraform.tfstate ]]; then
  echo "state bucket already exists"
  exit 0
fi

tofu -chdir=tofu/bootstrap init -input=false
tofu -chdir=tofu/bootstrap apply -input=false -auto-approve
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add tofu/bootstrap/terraform.tfstate tofu/bootstrap/.terraform.lock.hcl
git commit -m "Create the state bucket"
# Named, like every other push here: a bare one depends on the checkout
# having left a branch with an upstream, which is a property of the runner
# rather than of this repository.
git push origin "HEAD:${PUSH_BRANCH}"
