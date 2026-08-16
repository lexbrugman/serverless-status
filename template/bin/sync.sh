#!/usr/bin/env bash
# Rebuild everything the template owns from the pinned release, preserving
# what is yours: config.yaml, state.tfbackend, and the state and lock files.
# Everything under tofu/, bin/ and .github/ is replaced wholesale;
# tofu/grafana_org_<key>.tf and tofu/page.tf are generated from the
# release's stencil, one per key in config.yaml's grafana_orgs — hand edits
# to them do not survive a sync.
#
# Usage: sync.sh [REF]   (default: the ref pinned in tofu/page.tf)
set -euo pipefail

# Re-exec from a copy: the sync replaces this script itself.
if [[ "${SYNC_REEXEC:-}" != "1" ]]; then
  self_copy="$(mktemp)"
  cp "${BASH_SOURCE[0]}" "$self_copy"
  chmod +x "$self_copy"
  SYNC_REEXEC=1 exec "$self_copy" "$@"
fi

source_dir=""
target=""
ref=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    # A local template directory instead of the release clone — the
    # template's own tests use this.
    --source)
      source_dir="${2:?--source needs a directory}"
      shift 2
      ;;
    # The instance to render into. Set when a release's own copy of this
    # script has been handed the work.
    --target)
      target="${2:?--target needs a directory}"
      shift 2
      ;;
    *)
      ref="$1"
      shift
      ;;
  esac
done

ROOT="${target:-$(git rev-parse --show-toplevel)}"
cd "$ROOT"

# Wherever a past release kept the pin: an instance is synced by the
# release it is leaving, so this has to read a layout it may predate.
pin="$(git ls-files -- 'tofu/page.tf' 'page.tf' | head -n 1)"
if [[ -z "$ref" && -n "$pin" ]]; then
  ref="$(sed -n 's/.*?ref=\([^"]*\)".*/\1/p' "$pin" | head -n 1)"
fi
if [[ -z "$ref" ]]; then
  echo "ERROR: no ref given and no module pin found to read one from." >&2
  exit 1
fi

manifest_file=".sync-manifest"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if [[ -z "$source_dir" ]]; then
  # Upstream is wherever the modules are pinned: a fork that syncs from the
  # repository it does not use is the one split worth preventing.
  upstream="$(sed -n 's|.*"github.com/\([^/]*/[^/]*\)//modules/.*|\1|p' "${pin:-/dev/null}" | head -n 1)"
  if [[ -z "$upstream" ]]; then
    echo "ERROR: no module source found — the pin names the repository to sync from." >&2
    exit 1
  fi
  # A tag checkout is detached by definition; git's advice about it is for
  # someone who meant to work in the clone, and nobody works in this one.
  git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$ref" \
    "https://github.com/${upstream}" "$work/upstream"
  template="$work/upstream/template"
else
  template="$source_dir"
fi

# Hand the work to the release being adopted. An instance is always synced
# by the release it is leaving, so the copy that knows where this release
# keeps its stencil, its roots and its scripts is that release's own — this
# one knows only the layout it shipped with.
if [[ -z "$target" && -x "$template/bin/sync.sh" ]]; then
  exec "$template/bin/sync.sh" --target "$ROOT" --source "$template" "$ref"
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

# Inside the repository on purpose: the container wrapper resolves the
# root from the working directory and mounts only that, so a scratch root
# under /tmp would be invisible to it. Undotted so that an instance whose
# wrapper predates this still finds it.
reader="$ROOT/sync-reader"
rm -rf "$reader"
mkdir -p "$reader"
trap 'rm -rf "$work" "$reader"' EXIT
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
stencil="$(cd "$render" && find . -name 'grafana_org_example.tf' -printf '%P\n' | head -n 1)"
if [[ -z "$stencil" ]]; then
  echo "ERROR: the release has no grafana_org_example.tf to generate accounts from." >&2
  exit 1
fi
roots="$(dirname "$stencil")"

for org in "${orgs[@]}"; do
  {
    echo "# Generated from grafana_org_example.tf by bin/sync.sh for the"
    echo "# \"${org}\" account — hand edits do not survive a sync; changes"
    echo "# belong in config.yaml or upstream."
    sed "s/example/${org}/g" "$render/$stencil" | sed '0,/^$/d'
  } >"$work/grafana_org_${org}.tf"
done
rm "$render/$stencil"
for org in "${orgs[@]}"; do
  mv "$work/grafana_org_${org}.tf" "$render/${roots}/grafana_org_${org}.tf"
done

manifests=""
sources=""
for org in "${orgs[@]}"; do
  manifests+="module.checks_${org}.check_manifest, "
  sources+="module.checks_${org}.prometheus, "
done
sed -i "s|check_manifests    = \[.*\]|check_manifests    = [${manifests%, }]|" "$render/${roots}/page.tf"
sed -i "s|prometheus_sources = \[.*\]|prometheus_sources = [${sources%, }]|" "$render/${roots}/page.tf"

# State and lock files are yours and are never deleted, whatever the record
# says and wherever a past layout put them: a sync that strands one is
# untidy, a sync that removes one has destroyed the only copy of what
# exists.
protected='(^|/)(terraform\.tfstate(\.backup)?|\.terraform\.lock\.hcl)$'

# What is yours survives.
for file in config.yaml state.tfbackend; do
  if [[ -f "$file" ]]; then
    cp "$file" "$render/$file"
  fi
done
while IFS= read -r kept; do
  mkdir -p "$render/$(dirname "$kept")"
  cp "$kept" "$render/$kept"
done < <(git ls-files | grep -E "$protected" || true)

# What the previous sync generated is recorded, so what it generated is
# what gets removed — including from a layout this release no longer has.
# Anything added outside that record is untouched, and the first sync of an
# instance that predates the record falls back to the classes as they were.
if [[ -f "$manifest_file" ]]; then
  tr '\n' '\0' <"$manifest_file" | grep -zEv "$protected" | xargs -0 -r rm -f
else
  git ls-files -z -- 'tofu' 'bin' '.github' 'wiring' 'bootstrap' '*.tf' \
    'Containerfile' 'README.md' 'renovate.json' '.gitignore' 2>/dev/null |
    grep -zEv "$protected" | xargs -0 -r rm -f
fi
find . -mindepth 1 -type d -empty -not -path './.git/*' -delete 2>/dev/null || true

(cd "$render" && find . -type f -printf '%P\n' | sort |
  grep -Ev "$protected") >"$work/manifest"
cp -R "$render/." .
cp "$work/manifest" "$manifest_file"

echo "synced to ${ref} for accounts: ${orgs[*]}"
echo "Review with git status and git diff, then commit."
