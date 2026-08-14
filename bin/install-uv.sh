#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and local shells (dev-tools.sh).
set -euo pipefail

: "${UV_VERSION:?UV_VERSION must be set}"

install_dir="${1:?usage: install-uv.sh INSTALL_DIR [ARCH]}"
requested_arch="${2:-$(uname -m)}"

case "$requested_arch" in
  amd64 | x86_64) release_target="x86_64-unknown-linux-gnu" ;;
  arm64 | aarch64) release_target="aarch64-unknown-linux-gnu" ;;
  *)
    echo "Unsupported uv architecture: $requested_arch" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

asset="uv-${release_target}.tar.gz"
base="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"

curl -fsSLo "$tmp_dir/$asset" "$base/$asset"
curl -fsSLo "$tmp_dir/$asset.sha256" "$base/$asset.sha256"

expected="$(awk '{print $1}' "$tmp_dir/$asset.sha256")"
if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "No valid checksum found for $asset" >&2
  exit 1
fi
printf '%s  %s\n' "$expected" "$tmp_dir/$asset" | sha256sum -c -

tar -C "$tmp_dir" -xzf "$tmp_dir/$asset" "uv-${release_target}/uv"
mkdir -p "$install_dir"
install -m 0755 "$tmp_dir/uv-${release_target}/uv" "$install_dir/uv"
