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
- **Every guard is verified by mutation.** Break the tree once per guard,
  watch the run fail with that guard's message, restore. CI only ever runs
  over a compliant tree, so a guard silently unwired stays green everywhere;
  only a red run proves the wiring. This applies to the budget precondition,
  every `checks` validation, the manifest schema-version assertion, the
  identity sweep, the template-ref guard, and the empty-discovery guards in
  `lint.sh`.
- Module input validation is additionally covered by `.tftest.hcl` files
  using `expect_failures`, so invalid input being rejected is asserted
  automatically, not only mutation-verified.
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

## Where a new validation belongs

- Single-variable shape → `variable` `validation` block.
- Cross-value invariant that must hard-fail → `terraform_data` +
  `precondition`. `check` blocks are banned for invariants: they warn and
  neither fail a plan nor block an apply. `check` is for drift you want to
  *notice*, `precondition` for invariants you want to *enforce*.
- Repo-wide text rule → `scripts/lint.sh`.
- Renderer decision → pytest over a plain function.
- A value mirrored across layers → `scripts/check-cross-layer.py`.

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
  the Grafana stack, the state bucket). Destroying this stack must never be
  able to take down the zone.
- **`moved` blocks are mandatory on every refactor.** Master is release, so
  a restructure without one is a released landmine.
- **Providers are configured in roots only.** Modules declare
  `configuration_aliases`; a module that configures its own providers breaks
  `for_each` and makes clean destroys impossible.
- **No identity in the public repo**, enforced by the lint sweep.
- **Check configuration convention:** the type is the protocol, spelled out;
  `host` is a bare hostname; host, port, and path are separate facts.
  Unrepresentable invalid states beat validated ones — a scheme inside the
  target would be redundant with `type` at best and contradictory at worst.

## Accepted validation limitations

Named so they are known gaps rather than surprises.

- OpenTofu cannot prove a Grafana check definition is acceptable until
  apply, and cannot prove a probe reaches port 25 at all. The manual step
  zero (apply the SMTP checks alone, watch `probe_success`) is the gate, and
  nothing downstream is built until it passes.
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
