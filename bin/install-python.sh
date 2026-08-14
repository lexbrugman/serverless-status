#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and the toolbox (Containerfile).
#
# The interpreter the renderer targets (LAMBDA_PYTHON_VERSION). GitHub
# runners ship an older system Python, and 3.14-only syntax in the renderer
# is a SyntaxError there; anything that imports the renderer must run on the
# same minor the Lambda runtime does. Skipped where the environment already
# provides it (the toolbox base image); installed as uv's managed CPython
# otherwise.
set -euo pipefail

: "${LAMBDA_PYTHON_VERSION:?LAMBDA_PYTHON_VERSION must be set}"

install_dir="${1:?usage: install-python.sh INSTALL_DIR}"

if command -v python3 >/dev/null && [[ "$(python3 --version)" == "Python ${LAMBDA_PYTHON_VERSION}."* ]]; then
  echo "python ${LAMBDA_PYTHON_VERSION} already provided by the environment"
  exit 0
fi

"$(dirname "$0")/install-uv.sh" "$install_dir"
uv="$install_dir/uv"

"$uv" python install "$LAMBDA_PYTHON_VERSION"
# --system: without it, find prefers any virtual environment near the
# caller's working directory over the managed interpreter just installed.
python_bin="$("$uv" python find --system "$LAMBDA_PYTHON_VERSION")"
mkdir -p "$install_dir"
ln -sf "$python_bin" "$install_dir/python3"
