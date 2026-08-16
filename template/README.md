# serverless-status instance

The private root for a [serverless-status](https://github.com/lexbrugman/serverless-status)
page. Day-to-day changes happen in `status.yaml`; everything else is setup.

## Setup

The full walkthrough lives in the public repository's `docs/setup-guide.md`.
The short version — no local tooling beyond git and a browser:

1. **Grafana Cloud** — create the stack; create a provisioning access policy
   and token (scopes `accesspolicies:read|write|delete`, `stacks:read`),
   with an expiry, per organisation.
2. **Fill in your two files** — `status.yaml` (identity, accounts, checks,
   alerting) and `state.tfbackend` (the bucket and region, stated once).
   They are the only files you edit: everything else, `grafana_org_<key>.tf`
   and `page.tf` included, is generated from them by `bin/sync.sh`, which
   CI runs before every plan and apply.
3. **OIDC trust, by hand once** — create the GitHub OIDC provider and an
   admin role named `serverless-status-apply` in the AWS console; set the
   `APPLY_ROLE_ARN` variable and the `GRAFANA_CLOUD_TOKENS` and
   `STATE_PASSPHRASE` secrets in GitHub.
4. **Bootstrap from CI** — run the **Bootstrap** workflow once. It builds
   everything, gated in the middle by step zero: the SMTP dialogue is read
   back from the Synthetic Monitoring API and every SMTP check must report
   `probe_success` before anything downstream is built. Completing marks
   the repository bootstrapped, which switches routine CI on: PRs get a
   plan comment, master pushes apply.

## Upgrades

Renovate PRs bump the pinned release ref; CI rebuilds the template-owned
files from that release onto the same branch (`bin/sync.sh`), and the plan
comment reviews the result. `status.yaml`, `state.tfbackend`, and your
state always survive a sync.

## Working locally

For debugging only: `bin/tofu.sh` runs the release-pinned OpenTofu in a
container — alias it once per shell (`alias tofu="$PWD/bin/tofu.sh"`) and
nothing installs on the host.
