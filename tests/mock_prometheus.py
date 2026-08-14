#!/usr/bin/env python3
"""A Prometheus that always answers with a fixture state.

Importable by the test suite (class) and runnable inside the dev stack's
container (__main__), so the handler's HTTP path is exercised against the
same canned responses everywhere.
"""

import argparse
import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import fixtures


def responses_for(state_name: str, now: datetime) -> dict:
    prometheus = fixtures.load(state_name, now)["prometheus"]
    if prometheus is None:
        return {}
    return prometheus


class PrometheusHandler(BaseHTTPRequestHandler):
    responses: ClassVar[dict] = {}
    status_code = 200

    def log_message(self, *_args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query).get("query", [""])[0]
        if parsed.path == "/api/v1/query_range":
            payload = self.responses.get("duration_range")
        elif "probe_success" in query:
            payload = self.responses.get("success")
        else:
            payload = self.responses.get("duration")

        if self.status_code != 200 or payload is None:
            self.send_response(self.status_code if self.status_code != 200 else 503)
            self.end_headers()
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(state_name: str, port: int) -> ThreadingHTTPServer:
    PrometheusHandler.responses = responses_for(state_name, datetime.now(UTC).replace(tzinfo=None))
    server = ThreadingHTTPServer(("0.0.0.0", port), PrometheusHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="all-green", choices=fixtures.STATES)
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()
    server = serve(args.state, args.port)
    print(f"serving fixture {args.state} on :{args.port}")
    threading.Event().wait()
