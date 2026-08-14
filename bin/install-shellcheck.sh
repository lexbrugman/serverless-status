#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and the toolbox (Containerfile).
#
# Upstream publishes no checksum asset, so the download is verified against
# GitHub's release-asset digest — the fallback tier (AGENTS.md, Pinned tools).
set -euo pipefail

: "${SHELLCHECK_VERSION:?SHELLCHECK_VERSION must be set}"

install_dir="${1:?usage: install-shellcheck.sh INSTALL_DIR [ARCH]}"
requested_arch="${2:-$(uname -m)}"

case "$requested_arch" in
  amd64 | x86_64) release_arch="x86_64" ;;
  arm64 | aarch64) release_arch="aarch64" ;;
  *)
    echo "Unsupported shellcheck architecture: $requested_arch" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

asset="shellcheck-v${SHELLCHECK_VERSION}.linux.${release_arch}.tar.gz"
base="https://github.com/koalaman/shellcheck/releases/download/v${SHELLCHECK_VERSION}"

curl -fsSLo "$tmp_dir/$asset" "$base/$asset"
expected="$("$(dirname "$0")/fetch-release-asset-digest.sh" \
  koalaman/shellcheck "v${SHELLCHECK_VERSION}" "$asset")"
printf '%s  %s\n' "$expected" "$tmp_dir/$asset" | sha256sum -c -

tar -C "$tmp_dir" -xzf "$tmp_dir/$asset" "shellcheck-v${SHELLCHECK_VERSION}/shellcheck"
mkdir -p "$install_dir"
install -m 0755 "$tmp_dir/shellcheck-v${SHELLCHECK_VERSION}/shellcheck" "$install_dir/shellcheck"
