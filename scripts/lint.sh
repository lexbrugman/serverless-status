#!/usr/bin/env bash
# Lint the whole repository: shellcheck + shfmt over every shell script, ruff
# (lint + format) over every Python file, actionlint over workflows, tofu fmt
# over HCL, then the repo-specific sweeps. Behavior is file-configured
# (.shellcheckrc, .editorconfig, ruff.toml, .tflint.hcl) so local runs, CI,
# and editors all agree.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Tracked plus untracked non-ignored files, so a not-yet-committed file is
# linted locally before it can reach CI. Every discovery hard-errors when it
# returns empty: a rename must fail loudly, never silently skip checks.
discover() {
  git ls-files --cached --others --exclude-standard "$@"
}

require_found() {
  local what="$1" count="$2"
  if [[ "$count" -eq 0 ]]; then
    echo "ERROR: discovery returned no $what — a rename must fail loudly, not skip checks." >&2
    exit 1
  fi
}

mapfile -t shell_scripts < <(discover '*.sh')
require_found "shell scripts" "${#shell_scripts[@]}"

mapfile -t python_files < <(discover '*.py')
require_found "Python files" "${#python_files[@]}"

mapfile -t workflows < <(discover '.github/workflows/*.yml' '.github/workflows/*.yaml')
require_found "workflow files" "${#workflows[@]}"

echo "shellcheck (${#shell_scripts[@]} scripts)"
shellcheck "${shell_scripts[@]}"

echo "shfmt --diff (${#shell_scripts[@]} scripts)"
shfmt --diff "${shell_scripts[@]}"

echo "ruff check (${#python_files[@]} files)"
ruff check --no-cache "${python_files[@]}"

echo "ruff format --check"
ruff format --no-cache --check "${python_files[@]}"

echo "actionlint (${#workflows[@]} workflows)"
actionlint "${workflows[@]}"

echo "tofu fmt -check -recursive"
tofu fmt -check -recursive

# The operator identity must never appear in the public tree (AGENTS.md,
# Project agreements). The pattern is assembled from pieces so this script
# does not match itself.
identity_pattern="slim"
identity_pattern+="-it"
mapfile -t all_files < <(discover)
require_found "files" "${#all_files[@]}"
echo "identity sweep (${#all_files[@]} files)"
if grep -nIiE -- "$identity_pattern" "${all_files[@]}"; then
  echo "ERROR: operator identity found in the public tree (see matches above)." >&2
  exit 1
fi

echo "cross-layer version mirrors"
scripts/check-cross-layer.py

echo "Lint passed."
