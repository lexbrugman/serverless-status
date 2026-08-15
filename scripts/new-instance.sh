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

Next steps:
  1. Make it a repository: git init (skip if the target was a clone).
  2. Fill in the *.tfvars data files; the state bucket name appears
     once, in state.auto.tfvars.
  3. Secrets: the provisioning token comes from Grafana Cloud; the state
     passphrase is created here, once — generate it and store it in your
     password manager before exporting (every future plan and apply needs
     the same value):
       head -c 24 /dev/urandom | base64
       export TF_VAR_grafana_cloud_tokens='{ example = "..." }'
       export TF_VAR_state_passphrase=...
  4. Create the state bucket, then commit its state file:
       (cd bootstrap && tofu init && tofu apply -var-file=../state.auto.tfvars)
  5. tofu init -backend-config=state.auto.tfvars
  6. Step zero — apply the SMTP checks alone and verify port-25 egress and
     the stored dialogue order before anything else:
       tofu apply -target=module.checks_example
  7. After the full apply, hand CI the wheel: bin/ci-handover.sh
See docs/setup-guide.md in the public repository for the full walkthrough.
EOF
