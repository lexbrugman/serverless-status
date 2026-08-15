#!/usr/bin/env bash
# Applies the main root, stamping the page footer with the pinned release.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

module_ref="$(sed -n 's/.*?ref=\([^"]*\)".*/\1/p' page.tf | head -n 1)"
tofu init -input=false -backend-config=state.tfbackend
tofu apply -input=false -auto-approve -var "page_version=${module_ref}"
