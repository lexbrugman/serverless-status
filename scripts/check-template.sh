#!/usr/bin/env bash
# Validate the template as a root: a temp copy with module sources rewritten
# to local paths, which sidesteps the chicken-and-egg of validating a ref
# that does not exist yet. tflint runs with the repo-wide config.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cp -R "$ROOT/template/." "$tmp_dir/"
find "$tmp_dir" -name '*.tf' -print0 |
  xargs -0 sed -i "s|github.com/lexbrugman/serverless-status//modules/\([a-z]*\)?ref=master|$ROOT/modules/\1|g"

if grep -rn 'ref=master' "$tmp_dir" --include='*.tf'; then
  echo "ERROR: a module source survived the local-path rewrite (see above)." >&2
  exit 1
fi

cd "$tmp_dir"
tofu init -backend=false -input=false >/dev/null
tofu validate
tflint --config "$ROOT/.tflint.hcl"

echo "Template validates."
