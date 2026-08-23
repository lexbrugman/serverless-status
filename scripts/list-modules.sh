#!/usr/bin/env bash
# Every published module, as the JSON array a workflow matrix takes.
#
# Discovered rather than listed: a matrix that names its entries is a list
# that can go short without going empty, and a module nobody pointed the
# job at stays green while it accumulates whatever it likes. A shell glob,
# not a git pathspec — git matches without FNM_PATHNAME, so `modules/*/`
# there would reach into the submodules too.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

shopt -s nullglob
modules=(modules/*/)
shopt -u nullglob

if [[ ${#modules[@]} -eq 0 ]]; then
  echo "ERROR: no modules found — discovery must fail loudly, not skip checks." >&2
  exit 1
fi

modules=("${modules[@]%/}")
printf '["%s"' "${modules[0]}"
printf ',"%s"' "${modules[@]:1}"
printf ']\n'
