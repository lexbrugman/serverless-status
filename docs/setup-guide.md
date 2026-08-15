# Setup guide

From nothing to a live status page, with no local tooling beyond git and a
browser. Prerequisites: a Grafana Cloud account per organisation, an AWS
account, a Route 53 hosted zone for the parent domain, and a GitHub
repository for your private instance.

## 1. Grafana Cloud

1. Create a stack (Synthetic Monitoring is part of every stack).
2. Create an access policy with scopes `accesspolicies:read`,
   `accesspolicies:write`, `accesspolicies:delete`, `stacks:read`, and a
   token for it — **with an expiry**. This is the provisioning credential;
   it is the only Grafana secret that ever leaves Grafana, and it lives
   solely in the `GRAFANA_CLOUD_TOKENS` secret, keyed by org. Repeat per
   organisation when several accounts feed one page: each org keeps its own
   account, billing, and execution budget.

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
you cloned.

The instance separates what you own from what the template owns, in
three classes. The data files — `*.tfvars` and `state.tfbackend` — are
yours. `org_<key>.tf` and
`page.tf` are yours structurally — one org file per Grafana account,
copied from `org_example.tf`, plus that org's entry in `page.tf`'s two
lists; they also carry the module pins Renovate manages. Everything else —
`wiring/` and the root `.tf` shims marked "do not edit" — is logic a
template update overwrites wholesale. Fill in the data files:

- `instance.auto.tfvars` — who you are: domain, zone, site identity, your
  instance repository, and your Grafana account(s) keyed by org;
- `state.tfbackend` — where state lives: the bucket name and region,
  each stated exactly once;
- `checks.auto.tfvars` — what you monitor: your checks, each naming its
  org.

Create the state passphrase: a secret you invent once. It encrypts the
state client-side, and every future plan and apply needs this exact value.
Generate it and store it in your password manager:

```sh
head -c 24 /dev/urandom | base64
```

Losing the passphrase means losing the state: encryption is enforced, so an
unreadable state has no recovery path short of importing every resource
into a fresh one.

Commit the filled-in data files and push.

## 3. OIDC trust, by hand once

CI authenticates to AWS with OIDC from its very first run, so no AWS
credential is ever stored anywhere. The trust itself cannot create itself,
so two console creations come first — the first apply imports both and
manages them from then on, replacing the hand-made trust with the written
policy:

1. IAM → Identity providers → Add provider: OpenID Connect, URL
   `https://token.actions.githubusercontent.com`, audience
   `sts.amazonaws.com`.
2. IAM → Roles → Create role → Web identity: that provider, audience
   `sts.amazonaws.com`, your instance repository. Attach
   `AdministratorAccess` and name it exactly `serverless-status-apply` —
   the name is the adoption contract. Then open the role's *Trust
   relationships* and verify the subject condition is exactly

   ```json
   "StringLike": { "token.actions.githubusercontent.com:sub": "repo:<owner>/<repo>:*" }
   ```

   The wizard's filter fields often produce something narrower, and the
   bootstrap job authenticates with an environment-flavoured subject that
   a branch-filtered trust rejects. Organisations with immutable-ID
   subject claims spell the repository as `owner@id/name@id`, where the
   ids are numeric: the org id from
   `https://api.github.com/orgs/<owner>`, and the repository id — the API
   keeps private repositories behind a token — from the repo page's HTML
   source, in the `octolytics-dimension-repository_id` meta tag.
   Use that spelling both here and as `github_repository` in
   `instance.auto.tfvars`, or no pattern will match. The first apply
   replaces this policy with the managed one, narrowed to the production
   environment.

Then, in the instance repository, add the repository variable
`APPLY_ROLE_ARN` (the new role's ARN) and two repository secrets:
`GRAFANA_CLOUD_TOKENS` (the map from step 1, e.g.
`{ example = "<provisioning token>" }`) and `STATE_PASSPHRASE` (from
step 2).

## 4. Bootstrap from CI

Run the **Bootstrap** workflow (Actions → Bootstrap → Run workflow) with
phase `checks`. It creates the state bucket (committing the bootstrap
root's state back to the repository), adopts the hand-made trust, and
applies only the Grafana checks.

## 5. Step zero — SMTP first

The SMTP checks are the reason this design exists, and they are the one
thing OpenTofu cannot prove: whether the probes can egress port 25, and
whether the STARTTLS dialogue is stored in order. Nothing downstream is
built until this passes.

In the Grafana console (or via the Prometheus API): watch
`probe_success{job="<your smtp check>"}` report `1`, and confirm in the
Synthetic Monitoring UI that the check's TCP query/response steps read
greeting → EHLO → STARTTLS → upgrade → EHLO → QUIT in that order.

Applying only the checks first is the right mechanism here; an `enabled`
flag would be a permanent knob serving a one-time need.

## 6. Everything, and the handover

Run **Bootstrap** again with phase `all`. The apply blocks on ACM
certificate issuance, so a finished run is a working TLS endpoint. Its
summary lists the handover, verbatim:

- the repository variable `PLAN_ROLE_ARN` — setting it is also the
  switch that turns routine CI on: plan, apply, and drift jobs skip until
  it exists, so pushes during bootstrap stay inert;
- restrict the `production` environment's deployment branches to master
  (GitHub created the environment when the bootstrap referenced it; the
  restriction is what makes the apply role's environment-bound trust mean
  master only);
- the CloudFront hostname to verify the page and certificate on, before
  DNS points anywhere.

From then on: PRs get a plan comment, master pushes apply.

## 7. Cutover

Confirm the certificate from a device that never trusted the old page, then
repoint your status hostname. Leave any previous monitoring running as a
free second opinion.

## 8. Upgrading

Upgrades run themselves: the instance's Renovate opens a PR bumping the
pinned `?ref=`, and CI notices the bump and rebuilds everything the
template owns from that release, committed onto the same branch as "Sync
instance to <ref>". The plan comment then reviews the synced tree — the
tree the merge applies.

The rebuild is `bin/sync.sh`. Logic files are replaced wholesale (which
also removes files the release dropped); `org_<key>.tf` and `page.tf`
regenerate from the release's stencil over your existing org set — which
is why org files must stay stencil-pure: hand edits to them do not
survive a sync, and belong in the data files or upstream. Your data
files, the state and lock files, and anything you added outside the
template-owned classes are never touched.

One case needs a hand: when a release changes the workflow files
themselves, CI cannot push those (GitHub withholds workflow-write from
its own token) and the plan job fails saying so. Run `bin/sync.sh` on the
Renovate branch locally — it needs only git and sed — and push.

## Working locally

For debugging a bootstrap phase, or plans outside CI: `bin/tofu.sh` runs
OpenTofu in a container at exactly the version the pinned release's CI
tested — nothing installs on the host. Alias it once per shell; `TF_VAR_*`
and `AWS_*` variables pass through, and `~/.aws` mounts read-only:

```sh
alias tofu="$PWD/bin/tofu.sh"
export TF_VAR_grafana_cloud_tokens='{ example = "<provisioning token>" }'
export TF_VAR_state_passphrase=<the stored passphrase>
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...   # or AWS_PROFILE

(cd bootstrap && tofu init && tofu apply)
tofu init -backend-config=state.tfbackend
tofu apply -target=module.checks_example    # step zero, one per org
tofu apply
bin/ci-handover.sh                          # prints the handover values
```
