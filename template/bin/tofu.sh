#!/usr/bin/env bash
# OpenTofu in a container, at exactly the version the pinned release's CI
# tested — nothing on the host but a container runtime. Alias it once per
# shell and every documented command works verbatim, from any directory in
# the repository:
#
#   alias tofu="$PWD/bin/tofu.sh"
#
# The version derives from the module pin in tofu/page.tf — repository and ref
# both — so a Renovate bump moves tofu in lockstep, rebuilds the image
# exactly once, and a fork installs its own tooling rather than mine.
# TF_VAR_* and AWS_* environment variables pass through, and ~/.aws mounts
# read-only so profile and SSO credentials resolve.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

# Wherever the release in force keeps the pin: this wrapper is the one
# piece of tooling that has to work while a sync is moving things.
pin="$ROOT/tofu/page.tf"
if [[ ! -f "$pin" ]]; then
  pin="$ROOT/page.tf"
fi
module_ref="$(sed -n 's/.*?ref=\([^"]*\)".*/\1/p' "$pin" | head -n 1)"
module_repo="$(sed -n 's|.*"github.com/\([^/]*/[^/]*\)//modules/.*|\1|p' "$pin" | head -n 1)"
if [[ -z "$module_ref" || -z "$module_repo" ]]; then
  echo "ERROR: no module source found — the tofu version derives from the pin." >&2
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

input_hash="$(
  cat "$ROOT/Containerfile" <(printf '%s%s' "$module_repo" "$module_ref") |
    sha256sum | cut -c1-12
)"
image="localhost/serverless-status-instance-tofu:${input_hash}"

if ! "$runtime" image inspect "$image" >/dev/null 2>&1; then
  "$runtime" build \
    --build-arg "MODULE_REPO=${module_repo}" \
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
# bootstrap root works exactly like the main one. Assembled rather than
# pattern-stripped: a directory whose name begins with a dot is a real
# directory, not the repository root wearing a prefix.
relative="$(realpath --relative-to="$ROOT" "$PWD")"
workdir="/work"
if [[ "$relative" != "." ]]; then
  workdir="/work/${relative}"
fi

exec "$runtime" run --rm \
  "${stdio_args[@]}" \
  "${user_args[@]}" \
  "${mount_args[@]}" \
  -w "$workdir" \
  "${env_args[@]}" \
  "$image" "$@"
