#!/usr/bin/env python3
"""Assert cross-layer version mirrors agree.

The Lambda Python version is defined once in versions.env; every place that
cannot derive it mechanically carries a literal mirror instead, and each
mirror is pinned here so a half-landed bump fails lint (AGENTS.md: define
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

    if failures:
        sys.exit("ERROR: cross-layer version mirrors disagree:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
