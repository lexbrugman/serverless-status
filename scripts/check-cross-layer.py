#!/usr/bin/env python3
"""Assert cross-layer mirrors agree.

The Lambda Python version is defined once in versions.env, and the CI roles
are named once by the wiring that creates them; every place that cannot
derive those values mechanically carries a literal mirror instead, and each
mirror is pinned here so a half-landed change fails lint (AGENTS.md: define
once and derive; a mirror is the fallback, never the default).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (path, pattern, description) — the pattern's groups join with "." to form
# the mirrored version.
MIRRORS = [
    ("ruff.toml", r'^target-version = "py(\d)(\d+)"', "ruff target-version"),
    (
        "modules/renderer/lambda.tf",
        r'^\s*runtime\s*= "python(\d)\.(\d+)"',
        "Lambda runtime",
    ),
]


# The wiring names the roles it creates; a shell script cannot ask it, so
# every restatement is pinned here. A rename that lands in one place turns
# an assume or an import into a runtime failure nothing else catches.
ROLE_SOURCE = "template/tofu/wiring/ci/main.tf"
ROLE_MIRRORS = [
    (
        "apply",
        "template/bin/ci-bootstrap-gate.sh",
        r'^apply_role_name="([^"]+)"',
        "the apply role name",
    ),
    (
        "apply",
        "template/bin/ci-adopt-trust.sh",
        r"aws_iam_role\.apply'\s+(\S+)",
        "the imported apply role",
    ),
    (
        "plan",
        "template/bin/ci-bootstrap-gate.sh",
        r'^plan_role_name="([^"]+)"',
        "the plan role name",
    ),
]


# What "down" means is stated once in the renderer module's `page` variable
# and restated in the instance root, which has to resolve it before two
# consumers can be given the identical number. A backend-style default
# cannot be read out of a module from a root, so the restatement is forced;
# this is what stops the two drifting.
DOWN_DEFAULTS = [
    (
        "down_window_multiple",
        r"down_window_multiple = optional\(number, ([0-9.]+)\)",
        r"down_window_multiple = ([0-9.]+)",
    ),
    (
        "down_quorum",
        r"down_quorum          = optional\(number, ([0-9.]+)\)",
        r"down_quorum = ([0-9.]+)",
    ),
]
# The renderer publishes metrics through Influx, which names them
# <measurement>_<field>; the alert rules query those names as literals.
# A rule naming a metric nothing publishes returns no data forever, and
# no-data on the not-reporting rule is deliberately not an alert — so the
# mismatch is silent, and this is what makes it loud.
METRIC_SOURCE = "modules/renderer/src/report.py"
METRIC_RULES = "modules/alerting/main.tf"
METRIC_FIELDS = [
    (r'HEARTBEAT_FIELD = "([a-z_]+)"', "the heartbeat metric"),
    (r'OBSERVED_FIELD = "([a-z_]+)"', "the per-check metric"),
]

DOWN_MODULE = "modules/renderer/variables.tf"
DOWN_ROOT = "template/tofu/main.tf"


def read_role_names() -> dict[str, str]:
    names = {}
    for role in ("plan", "apply"):
        names[role] = extract(
            ROLE_SOURCE,
            rf'resource "aws_iam_role" "{role}" {{\s*\n\s*name\s*=\s*"([^"]+)"',
            f"the {role} role's name",
        )
    return names


def read_versions() -> dict[str, str]:
    versions = {}
    for line in (ROOT / "versions.env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        versions[key] = value
    return versions


def extract(path: str, pattern: str, description: str) -> str:
    """Pull a mirrored value out of a file, failing loudly when the file or
    the expected line is missing — a rename must never silently skip a check.
    """
    file = ROOT / path
    if not file.exists():
        sys.exit(f"ERROR: {path} not found — expected to hold {description}.")
    match = re.search(pattern, file.read_text(), re.MULTILINE)
    if not match:
        sys.exit(f"ERROR: no {description} found in {path} (expected pattern: {pattern}).")
    return ".".join(match.groups())


def main() -> None:
    lambda_python = read_versions()["LAMBDA_PYTHON_VERSION"]

    failures = []
    for path, pattern, description in MIRRORS:
        actual = extract(path, pattern, description)
        if actual != lambda_python:
            failures.append(
                f"{path}: {description} is {actual}, "
                f"versions.env LAMBDA_PYTHON_VERSION is {lambda_python}"
            )

    role_names = read_role_names()
    for role, path, pattern, description in ROLE_MIRRORS:
        actual = extract(path, pattern, description)
        if actual != role_names[role]:
            failures.append(
                f"{path}: {description} is {actual}, "
                f"{ROLE_SOURCE} names the {role} role {role_names[role]}"
            )

    for name, module_pattern, root_pattern in DOWN_DEFAULTS:
        declared = extract(DOWN_MODULE, module_pattern, f"the {name} default")
        resolved = extract(DOWN_ROOT, root_pattern, f"the resolved {name}")
        if declared != resolved:
            failures.append(
                f"{DOWN_ROOT}: {name} resolves to {resolved}, "
                f"{DOWN_MODULE} defaults it to {declared}"
            )

    measurement = extract(METRIC_SOURCE, r'MEASUREMENT = "([a-z_]+)"', "the Influx measurement")
    rules = (ROOT / METRIC_RULES).read_text()
    for pattern, description in METRIC_FIELDS:
        published = f"{measurement}_{extract(METRIC_SOURCE, pattern, description)}"
        if published not in rules:
            failures.append(
                f"{METRIC_RULES}: no rule queries {published}, which is what "
                f"{METRIC_SOURCE} publishes for {description}"
            )

    if failures:
        sys.exit("ERROR: cross-layer mirrors disagree:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
