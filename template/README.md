# serverless-status instance

The private root for a [serverless-status](https://github.com/lexbrugman/serverless-status)
page: Grafana Cloud probes your endpoints, AWS renders and serves the page,
and Grafana alerts you when something stays down.

## What is yours

Two files, and nothing else here is meant to be edited:

- `config.yaml` — the domain and its zone, the page's identity, where
  alerts go, your Grafana account(s), and every check;
- `state.tfbackend` — the state bucket and region, stated once. Separate
  because a backend is configured before any configuration is read.

Everything under `tofu/`, `bin/` and `.github/` is generated from those two
by `bin/sync.sh`, which CI runs before every plan and apply. Hand edits
there do not survive.

## Setup

The full walkthrough lives in the public repository's `docs/setup-guide.md`.
The short version — no local tooling beyond git and a browser:

1. **Grafana Cloud** — a stack per organisation, and a Cloud access policy
   on the organisation realm (scopes `accesspolicies:read|write|delete`,
   `stacks:read`, `stack-service-accounts:write`) with a token, kept in the
   `GRAFANA_CLOUD_TOKENS` secret.
2. **Fill in the two files above**, and invent the state passphrase that
   encrypts the state, kept in `STATE_PASSPHRASE`.
3. **OIDC trust, by hand once** — create the GitHub OIDC provider and an
   admin role named `serverless-status-apply` in the AWS console; its ARN
   goes in the `APPLY_ROLE_ARN` variable.
4. **Bootstrap from CI** — run the **Bootstrap** workflow once. It builds
   everything, gated in the middle by step zero: the SMTP dialogue is read
   back from the Synthetic Monitoring API and every check must publish a
   result before anything downstream is built. Completing marks the
   repository bootstrapped, which switches routine CI on.

## Day to day

Add a check, change a budget, redirect an alert: edit `config.yaml`, open a
pull request, read the plan comment, merge. Master pushes apply.

Renovate proposes each new release; CI rebuilds the generated files from it
on the same branch, so the plan you review is the tree that applies.
`config.yaml`, `state.tfbackend`, and your state always survive a sync.

## Working locally

Rarely needed — the bootstrap and every routine run happen in CI. For
reading state or planning by hand, `bin/tofu.sh` runs the release-pinned
OpenTofu in a container, so nothing installs on the host:

```sh
alias tofu="$PWD/bin/tofu.sh"
export TF_VAR_grafana_cloud_tokens='{ example = "<provisioning token>" }'
export TF_VAR_state_passphrase=<the stored passphrase>
export TF_VAR_github_repository=<owner>/<repo>   # CI reads this from its token
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...   # or AWS_PROFILE

tofu -chdir=tofu init -backend-config=../state.tfbackend
tofu -chdir=tofu plan
```
