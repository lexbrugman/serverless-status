#!/usr/bin/env bash
# Rebuild everything the template owns from the pinned release, preserving
# what is yours: config.yaml, state.tfbackend, and the state and lock files.
# Logic files are replaced wholesale; grafana_org_<key>.tf and page.tf are
# generated from the release's stencil, one per key in config.yaml's
# grafana_orgs — hand edits to them do not survive a sync.
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
  # Upstream is wherever the modules are pinned: a fork that syncs from the
  # repository it does not use is the one split worth preventing.
  upstream="$(sed -n 's|.*"github.com/\([^/]*/[^/]*\)//modules/.*|\1|p' page.tf | head -n 1)"
  if [[ -z "$upstream" ]]; then
    echo "ERROR: no module source in page.tf — it names the repository to sync from." >&2
    exit 1
  fi
  git clone --quiet --depth 1 --branch "$ref" "https://github.com/${upstream}" "$work/upstream"
  template="$work/upstream/template"
else
  template="$source_dir"
fi

# The account set, read from config.yaml by the YAML parser this stack
# already depends on rather than by pattern-matching the file: OpenTofu
# evaluates it in a scratch root with no providers and no backend, so a
# malformed file fails here with the parser's own message. Keys are sorted
# so the generated lists are stable.
tofu_bin="$(command -v tofu || true)"
if [[ -z "$tofu_bin" ]]; then
  tofu_bin="$ROOT/bin/tofu.sh"
fi

reader="$work/reader"
mkdir -p "$reader"
cp config.yaml "$reader/config.yaml"
cat >"$reader/main.tf" <<'READER'
output "org_keys" {
  value = sort(keys(yamldecode(file("${path.module}/config.yaml")).grafana_orgs))
}
READER
mapfile -t orgs < <(
  cd "$reader"
  "$tofu_bin" init -backend=false -input=false >/dev/null
  "$tofu_bin" apply -auto-approve -input=false >/dev/null
  "$tofu_bin" output -json org_keys | tr -d '[]" ' | tr ',' '\n'
)
if [[ ${#orgs[@]} -eq 0 || -z "${orgs[0]}" ]]; then
  echo "ERROR: no accounts under grafana_orgs in config.yaml." >&2
  exit 1
fi

# A fresh render of the template, refs stamped.
render="$work/render"
mkdir -p "$render"
cp -R "$template/." "$render/"
find "$render" -name '*.tf' -print0 | xargs -0 sed -i "s|?ref=master|?ref=${ref}|g"

# Account files from the stencil; the stencil's own header is replaced
# because a generated file's instructions are the sync's, not the copy-me
# note's.
for org in "${orgs[@]}"; do
  {
    echo "# Generated from grafana_org_example.tf by bin/sync.sh for the"
    echo "# \"${org}\" account — hand edits do not survive a sync; changes"
    echo "# belong in config.yaml or upstream."
    sed "s/example/${org}/g" "$render/grafana_org_example.tf" | sed '0,/^$/d'
  } >"$work/grafana_org_${org}.tf"
done
rm "$render/grafana_org_example.tf"
for org in "${orgs[@]}"; do
  mv "$work/grafana_org_${org}.tf" "$render/grafana_org_${org}.tf"
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
for file in config.yaml state.tfbackend .terraform.lock.hcl; do
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

echo "synced to ${ref} for accounts: ${orgs[*]}"
echo "Review with git status and git diff, then commit."
