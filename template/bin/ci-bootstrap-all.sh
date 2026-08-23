#!/usr/bin/env bash
# Applies everything, once step zero has proven the checks. The apply
# blocks on ACM certificate issuance, so a finished run is a working TLS
# endpoint.
#
# The bootstrap's apply is the routine one: same root, same plan, same
# config check before it. Restating those commands would be a second
# answer to what applying this instance means.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

exec bin/ci-apply.sh
