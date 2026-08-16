# Setup guide

From nothing to a live status page, with no local tooling beyond git and a
browser. Prerequisites: a Grafana Cloud account per organisation, an AWS
account, a Route 53 hosted zone for the parent domain, and a GitHub
repository for your private instance.

## 1. Grafana Cloud

1. Create a stack (Synthetic Monitoring is part of every stack).
2. Create a Cloud access policy from the **organisation's** Access
   Policies page, with the organisation as its realm — a policy scoped to
   a single stack, or an API key made inside the Grafana instance, cannot
   read the stack through the org-level API and every apply stops at
   `403 Forbidden`. Give it scopes `accesspolicies:read`,
   `accesspolicies:write`, `accesspolicies:delete`, and `stacks:read`
   (`stacks:delete` is not needed and nothing here should ever hold it),
   then create a token for it — **with an expiry**. This is the
   provisioning credential; it is the only Grafana secret that ever leaves
   Grafana, and it lives solely in the `GRAFANA_CLOUD_TOKENS` secret,
   keyed by org. Repeat per organisation when several accounts feed one
   page: each org keeps its own account, billing, and execution budget.

   Verify before going further — `200` means the token can do its job:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' \
     -H "Authorization: Bearer <token>" https://grafana.com/api/instances
   ```

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

The instance separates what you own from what the template owns, and you
own two files:

- `status.yaml` — everything about this instance: the domain and its zone,
  the page's identity, where alerts go, your Grafana account(s), and every
  check;
- `state.tfbackend` — where OpenTofu keeps its state: the bucket and
  region, each stated once. It is separate because a backend is configured
  before any configuration is read.

Everything else is generated. `grafana_org_<key>.tf` and `page.tf` come
from `status.yaml` — one file per Grafana account, plus that account's
entries in `page.tf`'s lists, carrying the module pins Renovate manages —
and `wiring/`, `bin/`, the workflows, and the root `.tf` shims are logic.
`bin/sync.sh` rewrites that whole class, and CI runs it before every plan
and apply, so hand edits outside your two files do not survive.

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
   source, in the `octolytics-dimension-repository_id` meta tag. Get this
   one wrong and the first assume is refused; it is the only place the
   spelling is yours to state, because from the adoption on the workflows
   read it out of the token itself. The bootstrap replaces this policy
   with the managed one, narrowed to the production environment.

Then, in the instance repository, add the repository variable
`APPLY_ROLE_ARN` (the new role's ARN — the only role ARN you ever state;
the read-only plan role's is derived from it) and two repository secrets:
`GRAFANA_CLOUD_TOKENS` (the map from step 1, keyed by the same account
identifiers `status.yaml` uses, e.g. `{ example = "<provisioning token>" }`)
and `STATE_PASSPHRASE` (from step 2).

## 4. Bootstrap

Run the **Bootstrap** workflow (Actions → Bootstrap → Run workflow). One
dispatch builds everything, with step zero as a gate in the middle:

1. it generates the account structure from `status.yaml` and commits it
   back, like every sync;
2. it creates the state bucket, committing that root's state back too;
3. it applies the Grafana checks — and nothing else;
4. **step zero**: it reads back what the Synthetic Monitoring API actually
   stored for each SMTP dialogue, prints it, and waits until every SMTP
   check has published a `probe_success` sample. That is the part
   OpenTofu cannot prove — that the checks exist *and* run. What the
   sample says is reported, not required: a page whose subject is down
   must still deploy, since reporting that is its job, and no metric
   distinguishes a blocked port from a server refusing today. A check
   that never publishes stops the run; a check publishing failure is
   named for you to judge in the Synthetic Monitoring UI, whose probe log
   shows how far the conversation got;
5. it adopts the hand-made trust, importing the console-created provider
   and role — only possible at this point, because an import evaluates the whole
   configuration and the Synthetic Monitoring providers are configured
   from what step 3 created;
6. it applies everything else. The apply blocks on ACM certificate
   issuance, so a finished run is a working TLS endpoint;
7. it marks the bootstrap complete, which is what switches routine CI on:
   plan, apply, and drift stay inert while the marker is absent, so pushes
   during a bootstrap cannot race it.

Every step is idempotent — a failed run is re-dispatched, not repaired.

The summary then names what is left, and it is not configuration: restrict
the `production` environment's deployment branches to master (GitHub
created the environment when the run referenced it; the restriction is
what makes the apply role's environment-bound trust mean master only), and
verify the page and its certificate on the CloudFront hostname it prints,
before DNS points anywhere.

From then on: PRs get a plan comment, master pushes apply.

## 5. Cutover

Confirm the certificate from a device that never trusted the old page, then
repoint your status hostname. Leave any previous monitoring running as a
free second opinion.

## 6. Upgrading

Upgrades run themselves: the instance's Renovate opens a PR bumping the
pinned `?ref=`, and the sync CI runs before every plan rebuilds everything
the template owns from that release, committing "Sync instance to <ref>"
onto the same branch. The plan comment then reviews the
synced tree — the tree the merge applies.

The rebuild is `bin/sync.sh`. Logic files are replaced wholesale (which
also removes files the release dropped); `grafana_org_<key>.tf` and
`page.tf` regenerate from the release's stencil, one per account in
`status.yaml`. Hand edits to generated files do not survive a sync —
changes belong in `status.yaml` or upstream. Your two files, the state and
lock files, and anything you added outside the template-owned classes are
never touched.

One case needs a hand: when a release changes the workflow files
themselves, CI cannot push those (GitHub withholds workflow-write from
its own token) and the plan job fails saying so. Run `bin/sync.sh` on the
Renovate branch locally and push.

## Working locally

Nothing here needs a local OpenTofu — the bootstrap and every routine run
happen in CI. For reading state or a plan outside CI, `bin/tofu.sh` runs
OpenTofu in a container at exactly the version the pinned release's CI
tested, so nothing installs on the host. Alias it once per shell;
`TF_VAR_*` and `AWS_*` variables pass through, and `~/.aws` mounts
read-only:

```sh
alias tofu="$PWD/bin/tofu.sh"
export TF_VAR_grafana_cloud_tokens='{ example = "<provisioning token>" }'
export TF_VAR_state_passphrase=<the stored passphrase>
# In CI this comes from the OIDC token; outside it, state it by hand —
# exactly as the trust policy spells it, or the plan proposes rewriting
# the trust.
export TF_VAR_github_repository=<owner>/<repo>
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...   # or AWS_PROFILE

tofu init -backend-config=state.tfbackend
tofu plan
```

The same secrets live in GitHub, where CI reads them; a local copy is a
convenience for debugging, never a requirement.
