#!/usr/bin/env bash
# Rebuild everything the template owns from the pinned release, preserving
# what is yours: the data files, the state and lock files, and your org
# set. Logic files are replaced wholesale; org_<key>.tf and page.tf are
# regenerated from the release's stencil over your existing org keys, so
# they must stay stencil-pure — hand edits to them do not survive a sync.
#
# Usage: sync.sh [REF]   (default: the ref pinned in page.tf)
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Re-exec from a copy: the sync replaces this script itself.
if [[ "${SYNC_REEXEC:-}" != "1" ]]; then
  self_copy="$(mktemp)"
  cp "${BASH_SOURCE[0]}" "$self_copy"
  chmod +x "$self_copy"
  SYNC_REEXEC=1 exec "$self_copy" "$@"
fi

repo_url="https://github.com/lexbrugman/serverless-status"
source_dir=""
ref=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    # A local template directory instead of the release clone — the
    # template's own tests use this.
    --source)
      source_dir="${2:?--source needs a directory}"
      shift 2
      ;;
    *)
      ref="$1"
      shift
      ;;
  esac
done

if [[ -z "$ref" ]]; then
  ref="$(sed -n 's/.*?ref=\([^"]*\)".*/\1/p' page.tf | head -n 1)"
fi
if [[ -z "$ref" ]]; then
  echo "ERROR: no ref given and none found in page.tf." >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if [[ -z "$source_dir" ]]; then
  git clone --quiet --depth 1 --branch "$ref" "$repo_url" "$work/upstream"
  template="$work/upstream/template"
else
  template="$source_dir"
fi

# The org set, read from the structural files themselves.
orgs=()
for file in org_*.tf; do
  key="${file#org_}"
  orgs+=("${key%.tf}")
done

# A fresh render of the template, refs stamped.
render="$work/render"
mkdir -p "$render"
cp -R "$template/." "$render/"
find "$render" -name '*.tf' -print0 | xargs -0 sed -i "s|?ref=master|?ref=${ref}|g"

# Org files from the stencil; the stencil's own header is replaced because
# a generated file's instructions are the sync's, not the copy-me note's.
for org in "${orgs[@]}"; do
  {
    echo "# Generated from org_example.tf by bin/sync.sh for org \"${org}\" —"
    echo "# hand edits do not survive a sync; changes belong in the data files"
    echo "# or upstream."
    sed "s/example/${org}/g" "$render/org_example.tf" | sed '0,/^$/d'
  } >"$work/org_${org}.tf"
done
rm "$render/org_example.tf"
for org in "${orgs[@]}"; do
  mv "$work/org_${org}.tf" "$render/org_${org}.tf"
done

manifests=""
sources=""
for org in "${orgs[@]}"; do
  manifests+="module.checks_${org}.check_manifest, "
  sources+="module.checks_${org}.prometheus, "
done
sed -i "s|check_manifests    = \[.*\]|check_manifests    = [${manifests%, }]|" "$render/page.tf"
sed -i "s|prometheus_sources = \[.*\]|prometheus_sources = [${sources%, }]|" "$render/page.tf"

# What is yours survives.
for file in instance.auto.tfvars checks.auto.tfvars state.tfbackend .terraform.lock.hcl; do
  if [[ -f "$file" ]]; then
    cp "$file" "$render/$file"
  fi
done
for file in bootstrap/terraform.tfstate bootstrap/terraform.tfstate.backup bootstrap/.terraform.lock.hcl; do
  if [[ -f "$file" ]]; then
    cp "$file" "$render/$file"
  fi
done

# Template-owned classes are removed before the render lands, so files the
# release dropped disappear instead of lingering; anything you added
# outside these classes is untouched.
git ls-files -z -- 'wiring' 'bin' '.github' 'bootstrap' '*.tf' \
  'Containerfile' 'README.md' 'renovate.json' '.gitignore' 2>/dev/null |
  xargs -0 -r rm -f
find wiring bin .github bootstrap -type d -empty -delete 2>/dev/null || true

cp -R "$render/." .

echo "synced to ${ref} for orgs: ${orgs[*]}"
echo "Review with git status and git diff, then commit."
