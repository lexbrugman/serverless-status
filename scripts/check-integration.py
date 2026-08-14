#!/usr/bin/env python3
"""Invoke the dev stack's Lambda exactly as Lambda does and assert the
response is a valid, fresh page. This is the only gate that runs the handler
under the real runtime — it exists for what moto cannot catch."""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import preview  # noqa: E402

INVOKE = "http://localhost:9000/2015-03-31/functions/function/invocations"


def invoke(attempts: int = 30) -> dict:
    last_error = None
    for _ in range(attempts):
        try:
            request = urllib.request.Request(INVOKE, data=b"{}", method="POST")
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except (urllib.error.URLError, OSError) as error:
            last_error = error
            time.sleep(1)
    sys.exit(f"ERROR: could not invoke the dev stack: {last_error}")


def main() -> None:
    result = invoke()
    if "errorMessage" in result:
        sys.exit(
            "ERROR: the handler raised under the real runtime:\n" + json.dumps(result, indent=2)
        )

    failures = []
    if result.get("statusCode") != 200:
        failures.append(f"statusCode is {result.get('statusCode')}")
    if result.get("degraded") is not False:
        failures.append("expected a non-degraded render against the mock Prometheus")
    if result.get("overall") != "operational":
        failures.append(f"overall is {result.get('overall')}")

    page = result.get("body") or ""
    failures += preview.validate_html(page)
    failures += [
        f"external reference: {u}"
        for u in preview.external_references(page, {"https://example.com"})
    ]
    if "vdev" not in page:
        failures.append("PAGE_VERSION did not reach the footer")

    if failures:
        sys.exit("ERROR: integration invoke failed:\n  " + "\n  ".join(failures))
    print(f"integration ok: overall={result['overall']}, bytes={result['bytes']}")


if __name__ == "__main__":
    main()
