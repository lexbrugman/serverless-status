# serverless-status instance

The private root for a [serverless-status](https://github.com/lexbrugman/serverless-status)
page. Day-to-day changes happen in `checks.auto.tfvars`; everything else is
setup.

## Bootstrap

The full walkthrough lives in the public repository's `docs/setup-guide.md`.
The short version:

1. **Grafana Cloud** — create the stack; create a provisioning access policy
   and token (scopes `accesspolicies:read|write|delete`, `stacks:read`),
   with an expiry.
2. **Fill in** `main.tf` locals, `ci.tf` locals, `orgs.auto.tfvars`,
   `checks.auto.tfvars` (every check names its org), and
   a state bucket name replacing `CHANGE-ME-state-bucket` everywhere it
   appears.
3. **State bucket** — `cd bootstrap && tofu init && tofu apply`, then
   commit the resulting `terraform.tfstate` (bucket metadata only, no
   secrets).
4. **First apply runs locally** with admin credentials (`ci.tf` creates the
   OIDC roles CI will later assume):

   ```sh
   head -c 24 /dev/urandom | base64   # the passphrase — store it, CI needs it too
   export TF_VAR_grafana_cloud_tokens='{ example = "..." }' TF_VAR_state_passphrase=...
   tofu init
   tofu apply -target=module.checks_example   # step zero: SMTP checks first
   ```

   Watch `probe_success` in Grafana to confirm the probes egress port 25,
   and verify the stored SMTP dialogue order, before applying the rest.
5. **Hand CI the wheel** — add `GRAFANA_CLOUD_TOKENS` (the full map) and `STATE_PASSPHRASE`
   as secrets on the protected `production` environment, the two role ARNs
   as `PLAN_ROLE_ARN` / `APPLY_ROLE_ARN` repository variables, and let
   master pushes apply from then on.
