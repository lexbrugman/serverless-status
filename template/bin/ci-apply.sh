#!/usr/bin/env bash
# Applies the main root. The page footer's version is derived from the
# pinned module ref in configuration, so this apply and every plan see the
# same value.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

tofu init -input=false -backend-config=state.tfbackend
tofu apply -input=false -auto-approve
