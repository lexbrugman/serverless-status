import json
from datetime import UTC, datetime

import boto3
import handler
import mock_prometheus
import pytest
import state
import store
from moto import mock_aws

TABLE = "status-page"
BUCKET = "status-page"
PARAM = "/status-page/prometheus"


@pytest.fixture
def prom_server():
    server = mock_prometheus.serve("all-green", 0)
    yield server
    server.shutdown()


@pytest.fixture
def aws(prom_server, monkeypatch):
    with mock_aws():
        dynamodb = boto3.client("dynamodb")
        dynamodb.create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3.client("s3")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        port = prom_server.server_address[1]
        boto3.client("ssm").put_parameter(
            Name=PARAM,
            Type="SecureString",
            Value=json.dumps(
                [
                    {
                        "query_url": f"http://127.0.0.1:{port}",
                        "user": "u",
                        "token": "t",
                        "write_token": "w",
                    }
                ]
            ),
        )
        monkeypatch.setenv("TABLE_NAME", TABLE)
        monkeypatch.setenv("BUCKET_NAME", BUCKET)
        monkeypatch.setenv("PROM_PARAM", PARAM)
        monkeypatch.setenv("PAGE_VERSION", "2026.814.0")
        monkeypatch.delenv("DDB_ENDPOINT", raising=False)
        monkeypatch.delenv("PROM_ENDPOINT", raising=False)
        handler._cache.clear()
        yield s3
        handler._cache.clear()


class TestHappyPath:
    def test_renders_and_publishes_everything(self, aws):
        result = handler.render_handler({}, None)
        assert result["statusCode"] == 200
        assert result["degraded"] is False
        assert result["overall"] == "operational"

        published = {key: aws.get_object(Bucket=BUCKET, Key=key) for key in handler.OBJECTS}
        page = published["index.html"]["Body"].read().decode()
        assert "All systems operational" in page
        assert "v2026.814.0" in page
        assert published["index.html"]["ContentType"] == "text/html; charset=utf-8"
        assert published["index.html"]["CacheControl"] == "public, max-age=30"
        assert json.loads(published["status.json"]["Body"].read())["overall"] == "operational"
        assert published["badge.svg"]["Body"].read().startswith(b"<svg")

        tbl = store.table(TABLE)
        latest = store.get_latest(tbl)
        assert latest["checks"]["website"]["up"] is True
        today = datetime.now(UTC).date().isoformat()
        rows = store.rollups(tbl, "website", today, today)
        assert rows[0]["samples"] == 1
        assert rows[0]["successes"] == 1

    def test_warm_invocation_reuses_credentials_and_manifest(self, aws):
        handler.render_handler({}, None)
        assert "sources" in handler._cache
        handler.render_handler({}, None)
        tbl = store.table(TABLE)
        today = datetime.now(UTC).date().isoformat()
        assert store.rollups(tbl, "website", today, today)[0]["samples"] == 2


class TestTransitions:
    def test_down_transition_opens_an_outage_and_recovery_closes_it(self, aws, prom_server):
        handler.render_handler({}, None)

        now = datetime.now(UTC).replace(tzinfo=None)
        down = mock_prometheus.responses_for("one-down", now)
        mock_prometheus.PrometheusHandler.responses = down
        result = handler.render_handler({}, None)
        assert result["overall"] == "partial_outage"
        tbl = store.table(TABLE)
        records = store.outages(tbl, "mail-inbound")
        assert len(records) == 1
        assert records[0]["ended_at"] is None

        mock_prometheus.PrometheusHandler.responses = mock_prometheus.responses_for(
            "all-green", now
        )
        result = handler.render_handler({}, None)
        assert result["overall"] == "operational"
        records = store.outages(tbl, "mail-inbound")
        assert records[0]["ended_at"] is not None
        assert records[0]["duration_seconds"] >= 0


class TestRecordHistory:
    def test_check_missing_from_metrics_writes_no_rollup(self, aws):
        tbl = store.table(TABLE)
        mani = handler.manifest()
        now = datetime.now(UTC)
        today = state.site_today(now, mani["site"]["timezone"])
        handler.record_history(tbl, mani, None, {"website": 1.0}, {}, now, today)
        day = today.isoformat()
        assert store.rollups(tbl, "website", day, day)[0]["samples"] == 1
        assert store.rollups(tbl, "api", day, day) == []

    def test_the_rollup_day_is_the_sites_not_utc(self):
        """22:30 UTC is already tomorrow in Amsterdam, and the bar the
        sample lands in has to agree with the clock on the page."""
        moment = datetime(2026, 8, 17, 22, 30, tzinfo=UTC)
        assert state.site_today(moment, "Europe/Amsterdam").isoformat() == "2026-08-18"


class TestDegraded:
    def test_prometheus_failure_renders_from_cache_and_writes_no_history(self, aws):
        handler.render_handler({}, None)
        tbl = store.table(TABLE)
        before = store.get_latest(tbl)

        mock_prometheus.PrometheusHandler.status_code = 503
        try:
            result = handler.render_handler({}, None)
        finally:
            mock_prometheus.PrometheusHandler.status_code = 200

        assert result["degraded"] is True
        assert result["overall"] == "operational"
        assert "Live monitoring data is currently unavailable" in result["body"]
        # The snapshot still holds the last real observation.
        assert store.get_latest(tbl) == before
        today = datetime.now(UTC).date().isoformat()
        assert store.rollups(tbl, "website", today, today)[0]["samples"] == 1

    def test_no_credentials_at_all_is_the_degraded_path(self, aws, monkeypatch):
        monkeypatch.delenv("PROM_PARAM")
        monkeypatch.delenv("BUCKET_NAME")
        handler._cache.clear()
        result = handler.render_handler({}, None)
        assert result["degraded"] is True
        assert result["overall"] == "unknown"

    def test_prom_endpoint_covers_the_dev_stack(self, aws, prom_server, monkeypatch):
        monkeypatch.delenv("PROM_PARAM")
        port = prom_server.server_address[1]
        monkeypatch.setenv("PROM_ENDPOINT", f"http://127.0.0.1:{port}")
        handler._cache.clear()
        result = handler.render_handler({}, None)
        assert result["degraded"] is False
        assert result["overall"] == "operational"


class TestMultipleSources:
    def test_sources_merge_by_job(self, aws, prom_server, monkeypatch):
        second = mock_prometheus.serve("all-green", 0)
        try:
            ports = (prom_server.server_address[1], second.server_address[1])
            boto3.client("ssm").put_parameter(
                Name=PARAM,
                Type="SecureString",
                Overwrite=True,
                Value=json.dumps(
                    [
                        {"query_url": f"http://127.0.0.1:{p}", "user": "u", "token": "t"}
                        for p in ports
                    ]
                ),
            )
            handler._cache.clear()
            result = handler.render_handler({}, None)
        finally:
            second.shutdown()
        assert result["degraded"] is False
        assert result["overall"] == "operational"

    def test_any_failing_source_degrades_the_whole_render(self, aws, prom_server, monkeypatch):
        port = prom_server.server_address[1]
        boto3.client("ssm").put_parameter(
            Name=PARAM,
            Type="SecureString",
            Overwrite=True,
            Value=json.dumps(
                [
                    {"query_url": f"http://127.0.0.1:{port}", "user": "u", "token": "t"},
                    {"query_url": "http://127.0.0.1:9", "user": "u", "token": "t"},
                ]
            ),
        )
        handler._cache.clear()
        result = handler.render_handler({}, None)
        assert result["degraded"] is True
