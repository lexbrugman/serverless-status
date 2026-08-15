#!/usr/bin/env bash
# Plans both roots with -detailed-exitcode: any drift fails the run.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu init -input=false -backend-config=state.tfbackend
tofu plan -input=false -detailed-exitcode
tofu -chdir=bootstrap init -input=false
tofu -chdir=bootstrap plan -input=false -detailed-exitcode
