#!/usr/bin/env bash
# Run a command in the toolbox container: every pinned tool available,
# nothing installed on the host but a container runtime. The image tag is a
# hash of its inputs (Containerfile, versions.env, bin/), so a version bump
# rebuilds exactly once and a stale toolbox can never run current checks.
#
# scripts/dev-stack.sh stays on the host on purpose: it drives the container
# runtime itself, and nesting runtimes buys nothing but pain.
#
# Usage: bootstrap-shell.sh [command...]   (no command: an interactive shell)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set -a
# shellcheck source=versions.env
source "$ROOT/versions.env"
set +a

runtime="${CONTAINER_RUNTIME:-}"
if [[ -z "$runtime" ]]; then
  if command -v podman >/dev/null 2>&1; then
    runtime="podman"
  elif command -v docker >/dev/null 2>&1; then
    runtime="docker"
  else
    echo "ERROR: neither podman nor docker found (or set CONTAINER_RUNTIME)." >&2
    exit 1
  fi
fi

input_hash="$(cat "$ROOT/Containerfile" "$ROOT/versions.env" "$ROOT"/bin/*.sh | sha256sum | cut -c1-12)"
image="localhost/serverless-status-toolbox:${input_hash}"

if ! "$runtime" image inspect "$image" >/dev/null 2>&1; then
  # Every versions.env entry is passed; the build warns about the ones the
  # Containerfile declares no ARG for (the dev-stack image tags), which is
  # the cheap side of never maintaining a second list.
  build_args=(--build-arg "PYTHON_VERSION=${LAMBDA_PYTHON_VERSION}")
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    build_args+=(--build-arg "${key}=${value}")
  done <"$ROOT/versions.env"
  "$runtime" build "${build_args[@]}" -t "$image" -f "$ROOT/Containerfile" "$ROOT" >&2
fi

user_args=(--user "$(id -u):$(id -g)")
if [[ "$runtime" == "podman" ]]; then
  user_args=(--userns=keep-id)
fi

# -i is unconditional so piped input reaches the command; -t only when both
# ends are a terminal.
stdio_args=(-i)
if [[ -t 0 && -t 1 ]]; then
  stdio_args+=(-t)
fi

if [[ $# -eq 0 ]]; then
  set -- bash
fi

exec "$runtime" run --rm \
  "${stdio_args[@]}" \
  "${user_args[@]}" \
  -v "$ROOT:/work" \
  -w /work \
  -e HOME=/tmp \
  "$image" "$@"
