#!/usr/bin/env bash
# Copy the template into a new private instance root, stamping the module
# refs to the latest release tag. The committed template deliberately floats
# on master (versions do not live in files humans maintain); the stamp
# happens here, once, at bootstrap.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

target="${1:?usage: new-instance.sh TARGET_DIR}"

# A fresh clone of an empty repository — a lone .git — is a valid target;
# any other content is not.
if [[ -d "$target" ]]; then
  shopt -s nullglob dotglob
  contents=("$target"/*)
  shopt -u nullglob dotglob
  for entry in "${contents[@]}"; do
    if [[ "${entry##*/}" != ".git" ]]; then
      echo "ERROR: $target exists and is not empty." >&2
      exit 1
    fi
  done
fi

tag="$(git -C "$ROOT" describe --tags --abbrev=0 2>/dev/null)" || {
  echo "ERROR: no release tag found — clone a released ref of this repository first." >&2
  exit 1
}

mkdir -p "$target"
cp -R "$ROOT/template/." "$target/"

find "$target" -name '*.tf' -print0 | xargs -0 sed -i "s|?ref=master|?ref=${tag}|g"

if grep -rn '?ref=master' "$target" --include='*.tf'; then
  echo "ERROR: a floating ref survived the stamp (see matches above)." >&2
  exit 1
fi

cat <<EOF
Instance created in $target, pinned to ${tag}.

Next steps (no local tooling needed — CI bootstraps over OIDC):
  1. Make it a repository: git init (skip if the target was a clone),
     add your private remote, push.
  2. Fill in config.yaml — the domain, the page, your Grafana
     account(s) and every check; the state bucket and region appear
     once, in state.tfbackend. Commit and push.
  3. In the IAM console: create the GitHub OIDC provider and a
     Web-identity role for this repository (branch filter empty),
     AdministratorAccess, named exactly serverless-status-apply.
  4. In GitHub: variable APPLY_ROLE_ARN; secrets GRAFANA_CLOUD_TOKENS
     (per-org map) and STATE_PASSPHRASE — generate it into your password
     manager first:
       head -c 24 /dev/urandom | base64
  5. Run the Bootstrap workflow. One dispatch builds everything, and
     step zero gates the middle of it: the SMTP dialogue is read back
     from the Synthetic Monitoring API and every check must publish a
     sample before anything downstream is built. Its summary lists what
     is left to do by hand.
See docs/setup-guide.md in the public repository for the full walkthrough.
EOF
