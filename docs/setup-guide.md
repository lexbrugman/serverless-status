# Setup guide

From nothing to a live status page. Prerequisites: a Grafana Cloud account
(free tier), an AWS account, a Route 53 hosted zone for the parent domain,
and a GitHub repository for your private instance.

## 1. Grafana Cloud

1. Create a stack (the free tier includes Synthetic Monitoring).
2. Create an access policy with scopes `accesspolicies:read`,
   `accesspolicies:write`, `accesspolicies:delete`, `stacks:read`, and a
   token for it — **with an expiry**. This is the provisioning credential;
   it is the only Grafana secret that ever leaves Grafana, and it lives
   solely in `TF_VAR_grafana_cloud_token`.

## 2. State bucket

Created out of band and deliberately unmanaged — a configuration does not
create its own state store:

```sh
aws s3api create-bucket --bucket <name> --region <region> \
  --create-bucket-configuration LocationConstraint=<region>
aws s3api put-bucket-versioning --bucket <name> \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket <name> \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 3. The instance

From a release checkout of this repository:

```sh
scripts/new-instance.sh ../my-status-instance
```

This copies the template and pins the module sources to the release you
cloned. Fill in:

- `main.tf` — domain, zone, stack slug, site identity;
- `providers.tf` — the state bucket and regions;
- `ci.tf` — your instance repository and the state bucket;
- `checks.auto.tfvars` — your checks.

Set the two secrets in your shell (never in a file):

```sh
export TF_VAR_grafana_cloud_token=<provisioning token>
export TF_VAR_state_passphrase=<16+ characters>
```

## 4. Step zero — SMTP first

The SMTP checks are the reason this design exists, and they are the one
thing OpenTofu cannot prove: whether the probes can egress port 25, and
whether the STARTTLS dialogue is stored in order. Nothing downstream is
built until this passes.

```sh
tofu init
tofu apply -target=module.checks
```

Then, in the Grafana console (or via the Prometheus API): watch
`probe_success{job="<your smtp check>"}` report `1`, and confirm in the
Synthetic Monitoring UI that the check's TCP query/response steps read
greeting → EHLO → STARTTLS → upgrade → EHLO → QUIT in that order.

`-target` is the right mechanism here; an `enabled` flag would be a
permanent knob serving a one-time need.

## 5. Full apply

```sh
tofu apply
```

The apply blocks on ACM certificate issuance, so a finished apply is a
working TLS endpoint. Verify the page on the `distribution_domain` output
before DNS points anywhere. The first apply runs locally with admin
credentials because `ci.tf` creates the OIDC roles CI will later assume.

## 6. Hand CI the wheel

In the instance repository, create the protected `production` environment,
then add:

- environment secrets `GRAFANA_CLOUD_TOKEN` and `STATE_PASSPHRASE`;
- repository variables `PLAN_ROLE_ARN` and `APPLY_ROLE_ARN` (from the first
  apply's IAM roles).

From then on: PRs get a plan comment, master pushes apply.

## 7. Cutover

Confirm the certificate from a device that never trusted the old page, then
repoint your status hostname. Leave any previous monitoring running as a
free second opinion.

## 8. The watcher

Create three HetrixTools uptime monitors against the finished page — by
hand, outside OpenTofu, so the dead-man's switch shares no blast radius with
what it watches. Its free tier requires a login every 90 days: set a
recurring 60-day calendar reminder now, before the reason is forgotten.
