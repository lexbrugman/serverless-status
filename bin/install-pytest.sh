#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and the toolbox (Containerfile).
#
# pypi pins by version, not checksum — a test-only dependency that ships
# nowhere. Installed into a venv under INSTALL_DIR so the tools stay as
# removable as every binary install; the venv is created by the pinned uv,
# which needs neither pip nor ensurepip on the host interpreter.
set -euo pipefail

: "${PYTEST_VERSION:?PYTEST_VERSION must be set}"
: "${PYTEST_COV_VERSION:?PYTEST_COV_VERSION must be set}"
: "${COVERAGE_VERSION:?COVERAGE_VERSION must be set}"
: "${BOTO3_VERSION:?BOTO3_VERSION must be set}"
: "${MOTO_VERSION:?MOTO_VERSION must be set}"

install_dir="${1:?usage: install-pytest.sh INSTALL_DIR}"

uv="$install_dir/uv"
if [[ ! -x "$uv" ]]; then
  "$(dirname "$0")/install-uv.sh" "$install_dir"
fi

venv_dir="$install_dir/.pytest-venv"
"$uv" venv --quiet --clear "$venv_dir"
"$uv" pip install --quiet --python "$venv_dir/bin/python" \
  "pytest==${PYTEST_VERSION}" \
  "pytest-cov==${PYTEST_COV_VERSION}" \
  "coverage==${COVERAGE_VERSION}" \
  "boto3==${BOTO3_VERSION}" \
  "moto==${MOTO_VERSION}"
ln -sf "$venv_dir/bin/pytest" "$install_dir/pytest"
