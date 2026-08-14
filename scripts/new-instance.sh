#!/usr/bin/env bash
# Copy the template into a new private instance root, stamping the module
# refs to the latest release tag. The committed template deliberately floats
# on master (versions do not live in files humans maintain); the stamp
# happens here, once, at bootstrap.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

target="${1:?usage: new-instance.sh TARGET_DIR}"

if [[ -e "$target" && -n "$(ls -A "$target" 2>/dev/null)" ]]; then
  echo "ERROR: $target exists and is not empty." >&2
  exit 1
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

Next steps:
  1. Fill in the locals in main.tf and ci.tf, the backend in providers.tf,
     and your checks in checks.auto.tfvars.
  2. export TF_VAR_grafana_cloud_token=...   (provisioning token)
     export TF_VAR_state_passphrase=...      (state encryption, >= 16 chars)
  3. tofu init
  4. Step zero — apply the SMTP checks alone and verify port-25 egress and
     the stored dialogue order before anything else:
       tofu apply -target=module.checks
See docs/setup-guide.md in the public repository for the full walkthrough.
EOF
