#!/usr/bin/env bash
# Applies everything, once step zero has proven the checks. The apply
# blocks on ACM certificate issuance, so a finished run is a working TLS
# endpoint.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu -chdir=tofu init -input=false -backend-config=../state.tfbackend
tofu -chdir=tofu plan -input=false -out=tfplan
bin/ci-check-config.py
tofu -chdir=tofu apply -input=false tfplan
