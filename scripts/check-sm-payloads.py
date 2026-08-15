#!/usr/bin/env python3
"""Assert the payloads the provider transmits to the SM API, one per check
type.

The wire payload is the one surface no plan, state, or test can observe —
it exists only inside the provider's API call during an apply. Two
invariants ride on it. The SMTP dialogue's entry order: the provider
serializes tcp query_response as a set sorted by an internal content hash,
and the dialogue module's spellings are crafted so that order equals
dialogue order. And the attribute mapping for every field the checks module
relies on: an https check that stops transmitting fail_if_not_ssl still
plans, applies, and probes green while asserting less than the page claims.

So this guard performs the call for real: it applies one check of each type
against a local mock of the SM API, using the provider version pinned in
the module's lock file, and asserts what arrived. A provider release that
scrambles the dialogue or drops a mapping turns this red instead of
silently weakening the monitoring.
"""

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_MODULE = ROOT / "modules" / "checks" / "dialogue"
LOCK_FILE = ROOT / "modules" / "checks" / ".terraform.lock.hcl"

# The non-smtp checks mirror what modules/checks/main.tf configures per
# type: fail_if_not_ssl and the accepted status code for https, an empty
# settings block for ping, frequency and timeout in milliseconds.
ROOT_CONFIG = """
terraform {
  required_providers {
    grafana = { source = "grafana/grafana", version = ">= 4.0" }
  }
}

provider "grafana" {
  sm_access_token = "mock-token"
  sm_url          = "http://127.0.0.1:%(port)d"
}

module "dialogue" {
  source = "%(dialogue)s"
}

output "declared" {
  value = module.dialogue.entries
}

resource "grafana_synthetic_monitoring_check" "smtp" {
  job       = "guard-smtp"
  target    = "mx.example.com:25"
  probes    = [11]
  frequency = 300000
  timeout   = 10000

  settings {
    tcp {
      tls = false
      dynamic "query_response" {
        for_each = module.dialogue.entries
        content {
          expect    = query_response.value.expect
          send      = query_response.value.send
          start_tls = query_response.value.start_tls
        }
      }
    }
  }
}

resource "grafana_synthetic_monitoring_check" "https" {
  job       = "guard-https"
  target    = "https://www.example.com/health"
  probes    = [11]
  frequency = 300000
  timeout   = 5000

  settings {
    http {
      fail_if_not_ssl    = true
      valid_status_codes = [200]
    }
  }
}

resource "grafana_synthetic_monitoring_check" "ping" {
  job       = "guard-ping"
  target    = "gw.example.com"
  probes    = [11]
  frequency = 600000
  timeout   = 3000

  settings {
    ping {}
  }
}
"""


class MockSMAPI(BaseHTTPRequestHandler):
    """Just enough of the SM API for checks to be created: probe listing,
    tenant lookup, and check/add — which records the payloads under test."""

    captured: ClassVar[list] = []

    def log_message(self, *_args):
        pass

    def _reply(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/probe/list" in self.path:
            self._reply(
                [
                    {
                        "id": 11,
                        "name": "Amsterdam",
                        "online": True,
                        "public": True,
                        "latitude": 0,
                        "longitude": 0,
                        "region": "EMEA",
                        "deprecated": False,
                        "labels": [],
                        "version": "v1",
                        "modified": 1,
                        "created": 1,
                    }
                ]
            )
        elif "/check/list" in self.path:
            self._reply([])
        else:
            self._reply({})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if "/check/add" in self.path:
            payload = json.loads(body)
            MockSMAPI.captured.append(payload)
            payload.update(
                {"id": 42 + len(MockSMAPI.captured), "tenantId": 1, "created": 1.0, "modified": 1.0}
            )
            self._reply(payload)
        else:
            self._reply({})


def tofu(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["tofu", *args], cwd=workdir, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: tofu {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result


def wire_entry(raw: dict) -> dict:
    return {
        "expect": base64.b64decode(raw.get("expect") or "").decode(),
        "send": base64.b64decode(raw.get("send") or "").decode(),
        "start_tls": bool(raw.get("startTLS", False)),
    }


def assert_smtp(payload: dict, declared: list) -> list[str]:
    sent = payload.get("settings", {}).get("tcp", {}).get("queryResponse")
    if not sent:
        return ["smtp: no query_response payload transmitted"]
    transmitted = [wire_entry(raw) for raw in sent]
    if transmitted != declared:
        return [
            "smtp: the dialogue arrived out of order — re-craft the spellings "
            "(see dialogue/main.tf) before this provider change ships.\n"
            f"  declared:    {json.dumps(declared)}\n"
            f"  transmitted: {json.dumps(transmitted)}"
        ]
    return []


def assert_https(payload: dict, _declared: list) -> list[str]:
    failures = []
    http = payload.get("settings", {}).get("http")
    if http is None:
        return ["https: no http settings transmitted"]
    if http.get("failIfNotSSL") is not True:
        failures.append(f"https: fail_if_not_ssl did not arrive true: {json.dumps(http)}")
    if http.get("validStatusCodes") != [200]:
        failures.append(f"https: valid_status_codes did not arrive as [200]: {json.dumps(http)}")
    if payload.get("target") != "https://www.example.com/health":
        failures.append(f"https: target arrived as {payload.get('target')!r}")
    return failures


def assert_ping(payload: dict, _declared: list) -> list[str]:
    if "ping" not in payload.get("settings", {}):
        return [f"ping: no ping settings transmitted: {json.dumps(payload.get('settings'))}"]
    return []


def assert_common(payload: dict) -> list[str]:
    """Frequency and timeout are milliseconds end to end."""
    expected = {
        "guard-smtp": (300000, 10000),
        "guard-https": (300000, 5000),
        "guard-ping": (600000, 3000),
    }
    frequency, timeout = expected[payload["job"]]
    failures = []
    if payload.get("frequency") != frequency:
        failures.append(f"{payload['job']}: frequency arrived as {payload.get('frequency')}")
    if payload.get("timeout") != timeout:
        failures.append(f"{payload['job']}: timeout arrived as {payload.get('timeout')}")
    return failures


ASSERTIONS = {
    "guard-smtp": assert_smtp,
    "guard-https": assert_https,
    "guard-ping": assert_ping,
}


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockSMAPI)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory(prefix="sm-payload-guard.") as tmp:
        workdir = Path(tmp)
        (workdir / "main.tf").write_text(
            ROOT_CONFIG % {"port": port, "dialogue": DIALOGUE_MODULE.as_posix()}
        )
        # The guard must exercise the provider version the module actually
        # pins, not whatever is newest today.
        if not LOCK_FILE.exists():
            sys.exit(f"ERROR: {LOCK_FILE} not found — expected the pinned provider lock.")
        shutil.copy(LOCK_FILE, workdir / ".terraform.lock.hcl")

        tofu(workdir, "init", "-backend=false", "-input=false")
        tofu(workdir, "apply", "-auto-approve", "-input=false")
        declared = json.loads(tofu(workdir, "output", "-json", "declared").stdout)

    server.shutdown()

    by_job = {payload.get("job"): payload for payload in MockSMAPI.captured}
    failures = []
    for job, check in ASSERTIONS.items():
        if job not in by_job:
            failures.append(f"{job}: never transmitted")
            continue
        failures += check(by_job[job], declared)
        failures += assert_common(by_job[job])

    if failures:
        sys.exit("ERROR: transmitted SM payloads diverge:\n  " + "\n  ".join(failures))

    print(f"SM payloads verified for {len(ASSERTIONS)} check types, dialogue order preserved.")


if __name__ == "__main__":
    main()
