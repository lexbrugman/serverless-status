"""What the renderer tells Grafana about its own run."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest
import report


class _Collector(BaseHTTPRequestHandler):
    received: ClassVar[list] = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        _Collector.received.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
                "body": body.decode(),
            }
        )
        self.send_response(204)
        self.end_headers()


@pytest.fixture
def collector():
    _Collector.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


class TestPayload:
    def test_heartbeat_alone_when_nothing_was_observed(self):
        assert report.payload(1755440000, None) == "status_page rendered_timestamp=1755440000"

    def test_one_gauge_per_check_sorted(self):
        lines = report.payload(1, {"b": True, "a": False}).splitlines()
        assert lines == [
            "status_page rendered_timestamp=1",
            "status_page,job=a observed=0",
            "status_page,job=b observed=1",
        ]


class TestWriteUrl:
    def test_write_path_replaces_the_query_path(self):
        assert (
            report.write_url("https://prometheus-prod-01.grafana.net/api/prom")
            == "https://prometheus-prod-01.grafana.net/api/v1/push/influx/write"
        )


class TestPublish:
    def test_posts_line_protocol_to_every_writable_source(self, collector):
        port = collector.server_address[1]
        sources = [
            {"query_url": f"http://127.0.0.1:{port}/api/prom", "user": "42", "write_token": "w"},
            # No write credential: nothing to report to.
            {"query_url": "http://127.0.0.1:1/api/prom", "user": "1", "token": "t"},
        ]
        assert report.publish(sources, "status_page rendered_timestamp=1") == []
        assert len(_Collector.received) == 1
        sent = _Collector.received[0]
        assert sent["path"] == report.WRITE_PATH
        assert sent["auth"] == "Bearer 42:w"
        assert sent["content_type"] == "text/plain"
        assert sent["body"] == "status_page rendered_timestamp=1"

    def test_an_unreachable_source_is_reported_not_raised(self):
        failures = report.publish(
            [{"query_url": "http://127.0.0.1:1/api/prom", "user": "u", "write_token": "w"}],
            "status_page rendered_timestamp=1",
        )
        assert len(failures) == 1
        assert "/api/v1/push/influx/write" in failures[0]


def test_the_payload_is_plain_text_not_json():
    """Influx line protocol, so the handler needs no encoder beyond str."""
    with pytest.raises(json.JSONDecodeError):
        json.loads(report.payload(1, {"a": True}))
