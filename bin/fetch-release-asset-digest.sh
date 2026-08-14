#!/usr/bin/env bash
# Print the SHA-256 GitHub computed for a release asset at upload (the API
# `digest` field). Fallback verification for installers whose upstream
# publishes no checksum asset: the same trust root as a release checksum file
# (the upstream repository plus GitHub), but it attests the bytes GitHub
# stored rather than the bytes the author built — so installers prefer the
# release's own checksum asset whenever one exists (AGENTS.md, Pinned tools).
#
# Sends GITHUB_TOKEN when set: unauthenticated api.github.com calls from
# shared CI-runner IPs are rate-limited.
set -euo pipefail

repo="${1:?usage: fetch-release-asset-digest.sh OWNER/REPO TAG ASSET}"
tag="${2:?usage: fetch-release-asset-digest.sh OWNER/REPO TAG ASSET}"
asset="${3:?usage: fetch-release-asset-digest.sh OWNER/REPO TAG ASSET}"

auth=()
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  auth=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

digest="$(
  curl -fsSL "${auth[@]}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${repo}/releases/tags/${tag}" |
    python3 -c '
import json
import sys

release = json.load(sys.stdin)
name = sys.argv[1]
for asset in release.get("assets", []):
    if asset.get("name") == name:
        print(asset.get("digest") or "")
' "$asset"
)"
digest="${digest#sha256:}"
if [[ ! "$digest" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "No usable release-asset digest for ${asset} in ${repo}@${tag}" >&2
  exit 1
fi
printf '%s\n' "$digest"
