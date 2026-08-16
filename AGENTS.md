# Working agreements

Conventions for changing this repository — human or AI. Architecture and
operations live in `README.md` and `docs/`. This file holds the agreements
that are not derivable from the code.

## Linting

- `scripts/lint.sh` (shellcheck + shfmt for shell, ruff lint+format for
  Python, actionlint for workflows, `tofu fmt` for HCL, plus the
  repo-specific sweeps) forms the lint-test gate in `ci.yml` together with
  the test suite: every other job executes these scripts, so nothing runs
  until they are clean and behave. Behavior is file-configured
  (`.shellcheckrc`, `.editorconfig`, `ruff.toml`, `.tflint.hcl`) so local
  runs, CI, and editors all agree. Run locally:
  `scripts/bootstrap-shell.sh scripts/lint.sh`.
- Fix findings by restructuring the code. An inline suppression
  (`# shellcheck disable`, `# noqa`) needs a genuinely unfixable false
  positive plus a written justification — as of today none exist, and adding
  the first one is a decision, not a convenience.
- actionlint resolves a `./.github/workflows/...` reference from the
  nearest git root, so the template's workflows are linted from a staged
  copy that is one; linting them in place reports every reusable workflow
  as missing.
- File discovery uses `git ls-files --cached --others --exclude-standard`,
  so uncommitted work is linted locally before it can reach CI, and every
  discovery hard-errors when it returns empty — a rename must fail loudly,
  never silently skip checks.
- The public tree carries no operator identity. The lint sweep enforces it;
  fixtures and examples use fictional names.

## Testing

- `scripts/test.sh` runs the pytest suite under `tests/` and `tofu test` in
  each module; it is the second half of the lint-test gate.
- Python product code (`modules/renderer/src`) carries **100% line and
  branch coverage**, enforced by `.coveragerc` (`fail_under = 100`); the
  gate fails on the first uncovered branch. Unreachable code is removed,
  not excluded — a `# pragma: no cover` needs the same written
  justification as a lint suppression, and none exist today.
- Outside that scope coverage is qualitative: scripts/ and the OpenTofu
  layer are process glue and declarations, covered by CI executing them for
  real and by `tofu test`. Do not add mocked tests to glue — they test the
  mocks.
- **Every guard is verified by mutation, without exception.** Break the
  tree once per guard, watch the run fail with that guard's own message,
  restore. CI only ever runs over a compliant tree, so a guard silently
  unwired stays green everywhere; only a red run proves the wiring. This
  covers preconditions, input validations, the repo-wide sweeps in
  `lint.sh`, and the payload and template assertions — a new guard is not
  finished until it has failed once on purpose.
- Module input validation is additionally covered by `.tftest.hcl` files
  using `expect_failures`, so invalid input being rejected is asserted
  automatically, not only mutation-verified.
- A test that runs a repository script builds its fixture from a
  disposable clone carrying a fake release tag. CI checks out without
  tags, so a suite that reads the real repository's tag state passes
  locally and fails there.
- In `tofu test`, each `run` states the `override_data` it needs. A
  file-level override of an address some run also overrides is ignored
  wherever that happens, and says so once per run.
- DynamoDB behavior is exercised with `moto` in-process; the main gate never
  requires a container runtime. The Lambda-runtime integration job exists
  precisely for what moto cannot catch: import errors, handler signature,
  runtime incompatibility.

## Pinned tools

- Every CLI the repo depends on is pinned once in `versions.env` with a
  `# renovate:` annotation. No tool version lives anywhere else.
- Every tool installs through one mechanism: a shared installer in `bin/`
  (`install-<tool>.sh`), consumed by CI via
  `.github/actions/setup-pinned-tools` and locally by the toolbox image
  (`Containerfile`, run via `scripts/bootstrap-shell.sh`). Nothing installs
  on the host: the toolbox tag hashes its inputs, so a version bump
  rebuilds it exactly once. A new tool is one installer plus a list entry —
  never an inline curl block, never a marketplace setup action.
- Installers verify every download, in two tiers. Preferred: the checksum
  asset the release itself publishes. A tool that publishes none verifies
  GitHub's release-asset digest instead, via
  `bin/fetch-release-asset-digest.sh` — the same trust root (the upstream
  repository plus GitHub) but attesting the bytes GitHub stored rather than
  the bytes the author built — a fallback where no checksum asset exists,
  never a substitute where one does. Each fallback installer says why at its
  download site. pytest is different in kind: pip installs it by pinned
  version, not a downloaded binary to checksum.
- Every workflow job carries `timeout-minutes`: a stalled download must fail
  the job rather than hang it for GitHub's six-hour default.

## Dependency pinning

- Actions are pinned by exact version tag, not commit SHA, and nothing is
  automerged anywhere: every dependency merge is human-reviewed, and
  readable tags are what keep that review meaningful.
- A value mirrored across layers (the Lambda Python version in
  `versions.env`, the OpenTofu `runtime` string, ruff's `target-version`) is
  defined once and derived where possible; where a literal mirror is forced,
  `scripts/check-cross-layer.py` pins it with a check. A mirror is the
  fallback, never the default.

## Shell discipline

- Shell orchestrates processes; Python makes decisions over structured data.
  A shell script that starts parsing structured data migrates to Python; a
  Python script that only sequences subprocesses migrates to shell.
- Every script starts `set -euo pipefail`, resolves the repo root
  (`git rev-parse --show-toplevel`, or `BASH_SOURCE` for the scripts that
  must work before or without git context), and is safe to run from any
  directory.
- Never `eval` constructed strings.
- Prefer running an existing engine over maintaining an equivalent; bespoke
  bridging code names its successor and is deleted at adoption. No
  speculative configuration: an env-var knob exists only when something
  actually sets it; a default that is the only value ever used is a
  constant.

## OpenTofu constraints

Behaviour that shapes this repository's structure. Each of these plans
cleanly and fails somewhere else, so none of them are discoverable from a
green plan.

- **`-backend-config` silently ignores a file named `*.auto.tfvars`** — no
  error, an empty bucket instead. Backend facts live in `state.tfbackend`,
  and because a backend block can read neither variables nor locals, every
  other consumer parses that same file with `file()` + `regex()`.
- **`tofu import` evaluates the whole configuration with nothing
  deferred.** An import cannot run while any provider configuration
  depends on resources that do not exist yet, which is why the bootstrap
  applies the Grafana checks before adopting the console-made trust.
- **`for_each` keys must be knowable without applying anything.** Key on
  inputs and put computed attributes in the map values; a map keyed on
  another resource's computed attribute plans fine and makes every import
  in the root impossible.
- **A precondition orders nothing by itself.** On a first apply a data
  source behind an unapplied resource is deferred, so the guard's
  precondition evaluates mid-apply — every resource a guard protects must
  `depends_on` it, or the guard races them instead of gating them.
- **A value passed with `-var` by one workflow is absent from every other
  plan** and reads as drift forever after. Derive it in configuration
  instead: the page footer's version is read from the module pin in
  `page.tf`.

## Where a new validation belongs

- Single-variable shape → `variable` `validation` block.
- Cross-value invariant that must hard-fail → `terraform_data` +
  `precondition`. `check` blocks are banned for invariants: they warn and
  neither fail a plan nor block an apply. `check` is for drift you want to
  *notice*, `precondition` for invariants you want to *enforce*.
- Repo-wide text rule → `scripts/lint.sh`.
- Renderer decision → pytest over a plain function.
- A value mirrored across layers → `scripts/check-cross-layer.py`.
- What the provider transmits → `scripts/check-sm-payloads.py`, which
  applies against a mock API and asserts the payload.
- What only the running system knows → a bootstrap verification step,
  asserting against the live API and the published metrics. Assert that
  monitoring works, never that what it monitors is healthy.

## Project agreements

- **Zero external page dependencies**, at render time and at view time. No
  CDN, no font host, no analytics, ever. The render tests assert the output
  contains no external reference outside the configured `site.links`.
- **Honest degradation.** If Prometheus is unreachable, render from the
  cached snapshot, flag `degraded` visibly, and write no history. Never a
  500, never stale green presented as current.
- **The deployment artifact is a zip**, built by `archive_file`. Containers
  are a test harness only; making the image the deploy artifact would be a
  design change, not an implementation detail.
- **Ownership boundary.** Modules create only what they own the entire
  lifecycle of, and read everything that predates them (the Route 53 zone,
  the Grafana stack). The state bucket belongs to the instance's separate
  `bootstrap/` root, whose state is committed to git — outside the main
  root's blast radius. Destroying this stack must never be able to take
  down the zone or its own state store.
- **`moved` blocks are mandatory on every refactor.** Master is release, so
  a restructure without one is a released landmine.
- **Providers are configured in roots only.** Modules declare
  `configuration_aliases`; a module that configures its own providers breaks
  `for_each` and makes clean destroys impossible.
- **No identity in the public repo**, enforced by the lint sweep.
- **Derive identity, declare intent.** Facts the system knows about itself
  are read, never configured: the repository as the OIDC token's `sub`
  claim spells it, the page version from the module pin, the plan role's
  ARN from the apply role's. Facts that state what the operator meant stay
  written down — the domain, the zone, which account runs a check, what
  budget it may spend. A derived identity cannot disagree with itself; a
  derived intention is a guess that happens to be right today.
- **The instance is generated, not copied.** `bin/sync.sh` rebuilds every
  template-owned file from the pinned release, and `org_<key>.tf` and
  `page.tf` come from the orgs map in `instance.auto.tfvars`. The three
  data files are the only thing an operator edits; hand edits anywhere
  else do not survive the next sync, which CI runs before every plan and
  apply. `GITHUB_TOKEN` may not write `.github/workflows`, so a release
  that changes them fails that push loudly and is finished by hand — the
  one case where a sync is not automatic.
- **Bootstrap is one dispatch, gated in the middle.** Step zero is
  machine-verified: the SMTP dialogue is read back from the Synthetic
  Monitoring API, and every check must publish a `probe_success` sample
  before anything downstream is built. The sample's *value* is never a
  gate — a page whose subject is down must still deploy, and no metric
  tells a blocked port from a service that is simply refusing. Its
  committed marker is what switches routine CI on, so pushes during a
  bootstrap stay inert instead of racing it.
- **Check configuration convention:** the type is the protocol, spelled out;
  `host` is a bare hostname; host, port, and path are separate facts.
  Unrepresentable invalid states beat validated ones — a scheme inside the
  target would be redundant with `type` at best and contradictory at worst.

## Accepted validation limitations

Named so they are known gaps rather than surprises.

- OpenTofu cannot prove a Grafana check definition is acceptable until
  apply, and cannot prove a probe reaches port 25 at all. Step zero
  (apply the SMTP checks alone, then verify) is the gate, and nothing
  downstream is built until it passes.
- What the Synthetic Monitoring backend stores is not necessarily what the
  provider sent it: `scripts/check-sm-payloads.py` asserts the
  transmission, the bootstrap reads the stored dialogue back, and only a
  live `probe_success` proves the conversation runs in order — a scrambled
  dialogue times out rather than reporting a failure that names itself.
- Probe locations are a live fleet, not a constant. A location that
  Grafana retires fails the plan by name; the module's default is only a
  starting point.
- The execution-budget arithmetic models Grafana's accounting rather than
  contracting with it; the default budget carries headroom for exactly this
  reason.
- `archive_file` zips the handler with no guarantee it imports under the
  real runtime. The integration job covers this, and is the reason it
  exists.
- CloudFront and ACM issuance cannot be validated offline; the apply blocks
  on certificate issuance instead.
- The page's client-side staleness banner depends on the viewer's clock. A
  badly skewed client may see a false staleness warning; the alternative —
  trusting the server clock alone — fails silently when the renderer dies,
  which is worse.

## Style

- Define once and derive; a mirror is the fallback, never the default, and
  every mirror is pinned by a check.
- Names match behaviour, call sites included.
- Comments state constraints the code cannot express, never the transition
  that produced them: a future reader sees only B, in the context of B.
- Docs state rules, not membership; versions never appear in prose.
- Commit subjects are one imperative line, no body, no trailers.
