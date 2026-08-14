#!/usr/bin/env bash
# Shared installer for CI (setup-pinned-tools) and the toolbox (Containerfile).
set -euo pipefail

: "${ACTIONLINT_VERSION:?ACTIONLINT_VERSION must be set}"

install_dir="${1:?usage: install-actionlint.sh INSTALL_DIR [ARCH]}"
requested_arch="${2:-$(uname -m)}"

case "$requested_arch" in
  amd64 | x86_64) release_arch="amd64" ;;
  arm64 | aarch64) release_arch="arm64" ;;
  *)
    echo "Unsupported actionlint architecture: $requested_arch" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

asset="actionlint_${ACTIONLINT_VERSION}_linux_${release_arch}.tar.gz"
base="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}"
curl -fsSLo "$tmp_dir/$asset" "$base/$asset"
curl -fsSLo "$tmp_dir/checksums.txt" "$base/actionlint_${ACTIONLINT_VERSION}_checksums.txt"
expected="$(awk -v f="$asset" '$2 == f {print $1}' "$tmp_dir/checksums.txt")"
if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "No valid checksum found for $asset" >&2
  exit 1
fi
printf '%s  %s\n' "$expected" "$tmp_dir/$asset" | sha256sum -c -

tar -C "$tmp_dir" -xzf "$tmp_dir/$asset" actionlint
mkdir -p "$install_dir"
install -m 0755 "$tmp_dir/actionlint" "$install_dir/actionlint"
