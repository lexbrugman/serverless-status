#!/usr/bin/env bash
# Plans the main root, keeping the output for the PR comment.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu init -input=false -backend-config=state.tfbackend
tofu plan -input=false -no-color -out=tfplan | tee plan.txt
