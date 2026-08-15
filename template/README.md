# serverless-status instance

The private root for a [serverless-status](https://github.com/lexbrugman/serverless-status)
page. Day-to-day changes happen in `checks.auto.tfvars`; everything else is
setup.

## Setup

The full walkthrough lives in the public repository's `docs/setup-guide.md`.
The short version — no local tooling beyond git and a browser:

1. **Grafana Cloud** — create the stack; create a provisioning access policy
   and token (scopes `accesspolicies:read|write|delete`, `stacks:read`),
   with an expiry, per organisation.
2. **Fill in the data files** — `instance.auto.tfvars` (identity and
   orgs), `state.tfbackend` (the bucket name, stated once), and
   `checks.auto.tfvars` (every check names its org). Your values live only
   in the data files; your structure lives only in `org_<key>.tf` (copy
   `org_example.tf` per Grafana account) and `page.tf`. Everything else —
   `wiring/`, `bin/`, the workflows, and the root files marked "do not
   edit" — is logic a sync overwrites.
3. **OIDC trust, by hand once** — create the GitHub OIDC provider and an
   admin role named `serverless-status-apply` in the AWS console; set the
   `APPLY_ROLE_ARN` variable and the `GRAFANA_CLOUD_TOKENS` and
   `STATE_PASSPHRASE` secrets in GitHub.
4. **Bootstrap from CI** — run the **Bootstrap** workflow: phase `checks`
   first (step zero: watch `probe_success` in Grafana and verify the
   stored SMTP dialogue order), then phase `all`. Its summary lists the
   handover; setting `PLAN_ROLE_ARN` switches routine CI on. From then on,
   PRs get a plan comment and master pushes apply.

## Upgrades

Renovate PRs bump the pinned release ref; CI rebuilds the template-owned
files from that release onto the same branch (`bin/sync.sh`), and the plan
comment reviews the result. Your data files, org set, and state always
survive a sync.

## Working locally

For debugging only: `bin/tofu.sh` runs the release-pinned OpenTofu in a
container — alias it once per shell (`alias tofu="$PWD/bin/tofu.sh"`) and
nothing installs on the host.
