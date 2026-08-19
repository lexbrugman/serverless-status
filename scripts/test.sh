#!/usr/bin/env bash
# Run the pytest suite (tests/), then `tofu test` in each module. Coverage is
# qualitative by agreement (AGENTS.md): decision-bearing functions are tested
# here; glue is covered by CI executing it for real.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# --cov last: it takes an optional value, so a path after it would become
# its argument and silently re-scope coverage away from .coveragerc.
pytest --quiet tests/ --cov

# The published modules and the instance wiring alike: both are OpenTofu
# that decides something, and both are testable without a provider.
#
# The suites are discovered, not the directories that might hold them. A
# directory list is a path that goes stale silently — a suite that stops
# being found looks exactly like one that passes — and discovery
# hard-errors when it comes up empty, the same rule scripts/lint.sh keeps.
mapfile -t suites < <(
  git ls-files --cached --others --exclude-standard '*.tftest.hcl' |
    xargs -r -n1 dirname | sed 's|/tests$||' | sort -u
)
if [[ ${#suites[@]} -eq 0 ]]; then
  echo "ERROR: no .tftest.hcl suites found — a rename must fail loudly, not skip tests." >&2
  exit 1
fi

echo "tofu test (${#suites[@]} suites)"
for module in "${suites[@]}"; do
  echo "tofu test (${module})"
  (cd "$module" && tofu init -backend=false -input=false >/dev/null && tofu test)
done
