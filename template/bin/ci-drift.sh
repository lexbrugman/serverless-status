#!/usr/bin/env bash
# Plans both roots with -detailed-exitcode: any drift fails the run.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu -chdir=tofu init -input=false -backend-config=../state.tfbackend
tofu -chdir=tofu plan -input=false -detailed-exitcode
tofu -chdir=tofu/bootstrap init -input=false
tofu -chdir=tofu/bootstrap plan -input=false -detailed-exitcode
