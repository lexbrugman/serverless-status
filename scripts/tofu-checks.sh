#!/usr/bin/env bash
# Validate one OpenTofu module directory: init without backend, validate,
# tflint with the repo-wide config. CI fans this out over the module matrix.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

target="${1:?usage: tofu-checks.sh MODULE_DIR}"
cd "$ROOT/$target"

tofu init -backend=false -input=false >/dev/null
tofu validate
tflint --config "$ROOT/.tflint.hcl"
