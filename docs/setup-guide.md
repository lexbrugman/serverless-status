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
   solely in `TF_VAR_grafana_cloud_tokens`, keyed by org. Repeat per
   organisation when several accounts feed one page: each org keeps its own
   account, billing, and free-tier budget.

## 2. The instance

The instance is its own private git repository, materialised from this
repository's template. Clone this repository at its newest release tag,
run the stamper, and make the result a repository:

```sh
git clone --branch <latest release tag> https://github.com/lexbrugman/serverless-status
serverless-status/scripts/new-instance.sh my-status-instance
cd my-status-instance
git init
git remote add origin <your private repository URL>
```

A fresh clone of an empty private repository also works as the target —
`new-instance.sh` accepts a directory containing only `.git`, and the
`git init`/`git remote` steps fall away.

The stamper copies the template and pins the module sources to the release
you cloned. Everything from here on happens inside the instance. Fill in:

- `main.tf` — domain, zone, site identity;
- `orgs.auto.tfvars` — your Grafana account(s), keyed by org;
- `checks.auto.tfvars` — your checks, each naming its org;
- `ci.tf` — your instance repository;
- the regions in `providers.tf` and `bootstrap/main.tf`;
- the state bucket name: pick one and replace `CHANGE-ME-state-bucket`
  everywhere it appears (`bootstrap/main.tf`, `providers.tf`, `ci.tf` — a
  backend block cannot read variables, so the name is a literal in three
  places).

Set the two secrets in your shell (never in a file). The provisioning
token is the one from step 1. The state passphrase is a secret you create
right here: it encrypts the state client-side, and every future plan and
apply — yours and CI's — needs this exact value. Generate it once, store
it in your password manager, and only then export it (it returns in step 6
as the `STATE_PASSPHRASE` environment secret):

```sh
head -c 24 /dev/urandom | base64        # the passphrase — store it first
export TF_VAR_grafana_cloud_tokens='{ example = "<provisioning token>" }'
export TF_VAR_state_passphrase=<the stored passphrase>
```

Losing the passphrase means losing the state: encryption is enforced, so an
unreadable state has no recovery path short of importing every resource
into a fresh one.

## 3. State bucket

The bucket belongs to the instance's separate `bootstrap/` root, so the
main stack can never delete its own state store. That root's state is a
local file committed to the repository: git predates everything, and the
file holds only bucket metadata, no secrets.

```sh
cd bootstrap
tofu init
tofu apply                       # admin credentials, once
git add terraform.tfstate
git commit -m "Create the state bucket"
cd ..
```

The daily drift workflow re-plans this root read-only, so a console change
to the bucket is found the next morning like any other drift.

## 4. Step zero — SMTP first

The SMTP checks are the reason this design exists, and they are the one
thing OpenTofu cannot prove: whether the probes can egress port 25, and
whether the STARTTLS dialogue is stored in order. Nothing downstream is
built until this passes.

```sh
tofu init
tofu apply -target=module.checks_example
```

(One `-target` per org module when several accounts feed the page.)

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

- environment secrets `GRAFANA_CLOUD_TOKENS` (the full map) and `STATE_PASSPHRASE`;
- repository variables `PLAN_ROLE_ARN` and `APPLY_ROLE_ARN` (from the first
  apply's IAM roles).

From then on: PRs get a plan comment, master pushes apply.

## 7. Cutover

Confirm the certificate from a device that never trusted the old page, then
repoint your status hostname. Leave any previous monitoring running as a
free second opinion.
