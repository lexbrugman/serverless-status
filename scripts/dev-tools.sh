#!/usr/bin/env bash
# Install every pinned tool into .tools/ via the shared installers in bin/,
# then print the PATH line to export. The tool set is discovered from the
# installers themselves, so a new tool is one installer plus a versions.env
# entry — never a list edit here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set -a
# shellcheck source=versions.env
source "$ROOT/versions.env"
set +a

install_dir="$ROOT/.tools"

for installer in "$ROOT"/bin/install-*.sh; do
  tool="$(basename "$installer" .sh)"
  echo "${tool#install-}"
  "$installer" "$install_dir"
done

echo
echo "Tools installed. Add them to your shell:"
echo "  export PATH=\"$install_dir:\$PATH\""
