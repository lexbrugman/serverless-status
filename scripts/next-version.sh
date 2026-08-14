#!/usr/bin/env bash
# The next CalVer tag: YYYY.MDD.PATCH — simultaneously valid semver (three
# numeric identifiers, no leading zeros) and chronologically ordered under
# semver comparison, so Renovate and OpenTofu constraints need no custom
# versioning configuration.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

day="$(date -u +%Y.%-m%d)"
last="$(git tag --list "${day}.*" | sed "s/^${day}\.//" | sort -n | tail -1)"
echo "${day}.$((${last:--1} + 1))"
