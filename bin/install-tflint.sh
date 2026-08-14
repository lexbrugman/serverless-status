#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and local shells (dev-tools.sh).
set -euo pipefail

: "${TFLINT_VERSION:?TFLINT_VERSION must be set}"

install_dir="${1:?usage: install-tflint.sh INSTALL_DIR [ARCH]}"
requested_arch="${2:-$(uname -m)}"

case "$requested_arch" in
  amd64 | x86_64) release_arch="amd64" ;;
  arm64 | aarch64) release_arch="arm64" ;;
  *)
    echo "Unsupported tflint architecture: $requested_arch" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

asset="tflint_linux_${release_arch}.zip"
base="https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}"
curl -fsSLo "$tmp_dir/$asset" "$base/$asset"
curl -fsSLo "$tmp_dir/checksums.txt" "$base/checksums.txt"
expected="$(awk -v f="$asset" '$2 == f {print $1}' "$tmp_dir/checksums.txt")"
if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "No valid checksum found for $asset" >&2
  exit 1
fi
printf '%s  %s\n' "$expected" "$tmp_dir/$asset" | sha256sum -c -

unzip -q "$tmp_dir/$asset" -d "$tmp_dir/tflint"
mkdir -p "$install_dir"
install -m 0755 "$tmp_dir/tflint/tflint" "$install_dir/tflint"
