#!/usr/bin/env bash
# OpenTofu in a container, at exactly the version the pinned release's CI
# tested — nothing on the host but a container runtime. Alias it once per
# shell and every documented command works verbatim, from any directory in
# the repository:
#
#   alias tofu="$PWD/bin/tofu.sh"
#
# The version derives from the module ref in page.tf, so a Renovate ref
# bump moves tofu in lockstep and rebuilds the image exactly once.
# TF_VAR_* and AWS_* environment variables pass through, and ~/.aws mounts
# read-only so profile and SSO credentials resolve.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

module_ref="$(sed -n 's/.*?ref=\([^"]*\)".*/\1/p' "$ROOT/page.tf" | head -n 1)"
if [[ -z "$module_ref" ]]; then
  echo "ERROR: no module ?ref= found in page.tf — the tofu version derives from it." >&2
  exit 1
fi

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

input_hash="$(cat "$ROOT/Containerfile" <(printf '%s' "$module_ref") | sha256sum | cut -c1-12)"
image="localhost/serverless-status-instance-tofu:${input_hash}"

if ! "$runtime" image inspect "$image" >/dev/null 2>&1; then
  "$runtime" build \
    --build-arg "MODULE_REF=${module_ref}" \
    -t "$image" -f "$ROOT/Containerfile" "$ROOT" >&2
fi

user_args=(--user "$(id -u):$(id -g)")
if [[ "$runtime" == "podman" ]]; then
  user_args=(--userns=keep-id)
fi

# -i is unconditional so piped input reaches tofu; -t only when both ends
# are a terminal (apply's approval prompt needs it).
stdio_args=(-i)
if [[ -t 0 && -t 1 ]]; then
  stdio_args+=(-t)
fi

env_args=(-e HOME=/tmp)
while IFS='=' read -r name _; do
  case "$name" in
    TF_VAR_* | AWS_*) env_args+=(-e "$name") ;;
  esac
done < <(env)

mount_args=(-v "$ROOT:/work")
if [[ -d "$HOME/.aws" ]]; then
  mount_args+=(-v "$HOME/.aws:/tmp/.aws:ro")
fi

# Run in the same directory relative to the repository root, so the
# bootstrap root works exactly like the main one.
relative="$(realpath --relative-to="$ROOT" "$PWD")"

exec "$runtime" run --rm \
  "${stdio_args[@]}" \
  "${user_args[@]}" \
  "${mount_args[@]}" \
  -w "/work/${relative#.}" \
  "${env_args[@]}" \
  "$image" "$@"
