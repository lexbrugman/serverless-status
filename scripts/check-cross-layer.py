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
ROLE_SOURCE = "template/wiring/ci/main.tf"
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

    if failures:
        sys.exit("ERROR: cross-layer mirrors disagree:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
