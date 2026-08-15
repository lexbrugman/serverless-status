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
2. **State bucket** — replace `CHANGE-ME-state-bucket` everywhere it
   appears, then `cd bootstrap && tofu init && tofu apply` and commit the
   resulting `terraform.tfstate` (bucket metadata only, no secrets).
3. **Fill in** `main.tf` locals, `ci.tf` locals, and `checks.auto.tfvars`.
4. **First apply runs locally** with admin credentials (`ci.tf` creates the
   OIDC roles CI will later assume):

   ```sh
   export TF_VAR_grafana_cloud_token=... TF_VAR_state_passphrase=...
   tofu init
   tofu apply -target=module.checks   # step zero: SMTP checks first
   ```

   Watch `probe_success` in Grafana to confirm the probes egress port 25,
   and verify the stored SMTP dialogue order, before applying the rest.
5. **Hand CI the wheel** — add `GRAFANA_CLOUD_TOKEN` and `STATE_PASSPHRASE`
   as secrets on the protected `production` environment, the two role ARNs
   as `PLAN_ROLE_ARN` / `APPLY_ROLE_ARN` repository variables, and let
   master pushes apply from then on.
