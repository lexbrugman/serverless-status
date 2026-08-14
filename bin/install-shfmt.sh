#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and local shells (dev-tools.sh).
#
# Upstream publishes no checksum asset, so the download is verified against
# GitHub's release-asset digest — the fallback tier (AGENTS.md, Pinned tools).
set -euo pipefail

: "${SHFMT_VERSION:?SHFMT_VERSION must be set}"

install_dir="${1:?usage: install-shfmt.sh INSTALL_DIR [ARCH]}"
requested_arch="${2:-$(uname -m)}"

case "$requested_arch" in
  amd64 | x86_64) release_arch="amd64" ;;
  arm64 | aarch64) release_arch="arm64" ;;
  *)
    echo "Unsupported shfmt architecture: $requested_arch" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

asset="shfmt_v${SHFMT_VERSION}_linux_${release_arch}"
curl -fsSLo "$tmp_dir/shfmt" \
  "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/$asset"
expected="$("$(dirname "$0")/fetch-release-asset-digest.sh" \
  mvdan/sh "v${SHFMT_VERSION}" "$asset")"
printf '%s  %s\n' "$expected" "$tmp_dir/shfmt" | sha256sum -c -

mkdir -p "$install_dir"
install -m 0755 "$tmp_dir/shfmt" "$install_dir/shfmt"
