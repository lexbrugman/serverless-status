from datetime import datetime

import mock_prometheus
import prometheus
import pytest

NOW = datetime(2026, 8, 14, 12, 0, 0)


@pytest.fixture
def server():
    instance = mock_prometheus.serve("all-green", 0)
    yield instance
    instance.shutdown()
    mock_prometheus.PrometheusHandler.status_code = 200


def credentials(server):
    port = server.server_address[1]
    return {"query_url": f"http://127.0.0.1:{port}", "user": "u", "token": "t"}


class TestHTTP:
    def test_instant_queries_parse_to_job_maps(self, server):
        success = prometheus.instant(credentials(server), prometheus.INSTANT_SUCCESS, NOW)
        assert success["website"] == 1.0
        duration = prometheus.instant(credentials(server), prometheus.INSTANT_DURATION, NOW)
        assert duration["website"] > 0

    def test_range_query_parses_to_series(self, server):
        series = prometheus.latency_range(credentials(server), NOW)
        assert len(series["website"]) == 96

    def test_http_error_raises_prometheus_error(self, server):
        mock_prometheus.PrometheusHandler.status_code = 500
        with pytest.raises(prometheus.PrometheusError, match="query"):
            prometheus.instant(credentials(server), prometheus.INSTANT_SUCCESS, NOW)

    def test_unreachable_endpoint_raises_prometheus_error(self):
        broken = {"query_url": "http://127.0.0.1:9", "user": "u", "token": "t"}
        with pytest.raises(prometheus.PrometheusError):
            prometheus.instant(broken, prometheus.INSTANT_SUCCESS, NOW)
