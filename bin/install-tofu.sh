#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and local shells (dev-tools.sh).
set -euo pipefail

: "${OPENTOFU_VERSION:?OPENTOFU_VERSION must be set}"

install_dir="${1:?usage: install-tofu.sh INSTALL_DIR [ARCH]}"
requested_arch="${2:-$(uname -m)}"

case "$requested_arch" in
  amd64 | x86_64) release_arch="amd64" ;;
  arm64 | aarch64) release_arch="arm64" ;;
  *)
    echo "Unsupported tofu architecture: $requested_arch" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

asset="tofu_${OPENTOFU_VERSION}_linux_${release_arch}.zip"
base="https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}"
curl -fsSLo "$tmp_dir/$asset" "$base/$asset"
curl -fsSLo "$tmp_dir/SHA256SUMS" "$base/tofu_${OPENTOFU_VERSION}_SHA256SUMS"
expected="$(awk -v f="$asset" '$2 == f {print $1}' "$tmp_dir/SHA256SUMS")"
if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "No valid checksum found for $asset" >&2
  exit 1
fi
printf '%s  %s\n' "$expected" "$tmp_dir/$asset" | sha256sum -c -

unzip -q "$tmp_dir/$asset" -d "$tmp_dir/tofu"
mkdir -p "$install_dir"
install -m 0755 "$tmp_dir/tofu/tofu" "$install_dir/tofu"
