#!/usr/bin/env bash
# Applies the main root. The page footer's version is derived from the
# pinned module ref in configuration, so this apply and every plan see the
# same value.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu -chdir=tofu init -input=false -backend-config=../state.tfbackend
# Planned to a file first so the config check reads the same plan that is
# applied, and so the apply is exactly what was reviewed.
tofu -chdir=tofu plan -input=false -out=tfplan
bin/ci-check-config.py
tofu -chdir=tofu apply -input=false tfplan
