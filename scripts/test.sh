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
for module in modules/*/ template/wiring/*/; do
  if compgen -G "${module}tests/*.tftest.hcl" >/dev/null; then
    echo "tofu test (${module})"
    (cd "$module" && tofu init -backend=false -input=false >/dev/null && tofu test)
  fi
done
