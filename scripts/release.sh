#!/usr/bin/env bash
# Tag and publish the release for HEAD. Master is release: every push that
# passes the gate lands here; nothing is ever tagged by hand, and the CI
# gate is the release review.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

version="$(scripts/next-version.sh)"

git tag "$version"
git push origin "$version"
gh release create "$version" --title "$version" --generate-notes

echo "released $version"
