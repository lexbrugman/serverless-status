#!/usr/bin/env bash
# Creates the state bucket and commits the bootstrap root's state back
# (bucket metadata only, no secrets). The committed state file is the
# done-marker: reruns skip.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ -f bootstrap/terraform.tfstate ]]; then
  echo "state bucket already exists"
  exit 0
fi

tofu -chdir=bootstrap init -input=false
tofu -chdir=bootstrap apply -input=false -auto-approve
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add bootstrap/terraform.tfstate bootstrap/.terraform.lock.hcl
git commit -m "Create the state bucket"
git push
