#!/usr/bin/env python3
"""Prove the SMTP dialogue reaches the SM API in declaration order.

The grafana provider stores tcp query_response blocks as a set and transmits
them sorted by an internal content hash. The dialogue module's spellings are
crafted so hash order equals dialogue order — an invariant no plan, state,
or test can observe, because it only exists inside the provider's API call.
So this guard performs that call for real: it applies a minimal check
against a local mock of the SM API, using the provider version pinned in the
module's lock file, and compares the transmitted order against the module's
declared order. A provider release that changes the hashing turns this red
instead of silently scrambling the conversation.
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
  job    = "dialogue-order-guard"
  target = "mx.example.com:25"
  probes = [11]

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
"""


class MockSMAPI(BaseHTTPRequestHandler):
    """Just enough of the SM API for one check to be created: probe listing,
    tenant lookup, and check/add — which records the payload we care about."""

    captured: ClassVar[dict] = {}

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
            MockSMAPI.captured = payload
            payload.update({"id": 42, "tenantId": 1, "created": 1.0, "modified": 1.0})
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


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockSMAPI)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory(prefix="smtp-dialogue-guard.") as tmp:
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
        declared_raw = tofu(workdir, "output", "-json", "declared").stdout

    server.shutdown()

    declared = json.loads(declared_raw)
    sent = MockSMAPI.captured.get("settings", {}).get("tcp", {}).get("queryResponse")
    if not sent:
        sys.exit("ERROR: mock SM API captured no query_response payload.")

    transmitted = [wire_entry(raw) for raw in sent]
    if transmitted != declared:
        sys.exit(
            "ERROR: the provider transmitted the SMTP dialogue out of order.\n"
            f"declared:    {json.dumps(declared)}\n"
            f"transmitted: {json.dumps(transmitted)}\n"
            "The dialogue module's spellings no longer sort into dialogue order "
            "under this provider version — re-craft them (see dialogue/main.tf) "
            "before this provider change ships."
        )

    print(f"SMTP dialogue order preserved across {len(transmitted)} entries.")


if __name__ == "__main__":
    main()
