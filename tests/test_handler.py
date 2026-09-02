import json
from datetime import UTC, datetime, timedelta

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
        mani = handler.manifest()
        today = state.site_today(datetime.now(UTC), mani["site"]["timezone"]).isoformat()
        rows = store.rollups(tbl, "website", today, today)
        # Recomputed from Prometheus rather than incremented per run, so the
        # day holds every execution so far and not one per render.
        assert rows[0]["samples"] > 1
        assert rows[0]["successes"] <= rows[0]["samples"]
        assert latest["processed_through"] is not None

    def test_warm_invocation_reuses_credentials_and_manifest(self, aws):
        handler.render_handler({}, None)
        assert "sources" in handler._cache
        tbl = store.table(TABLE)
        mani = handler.manifest()
        day = state.site_today(datetime.now(UTC), mani["site"]["timezone"]).isoformat()
        first = store.rollups(tbl, "website", day, day)[0]
        handler.render_handler({}, None)
        # A second run recomputes the same day from the same source, so the
        # totals do not move. An increment would have doubled them.
        assert store.rollups(tbl, "website", day, day)[0] == first


class TestTransitions:
    def test_down_transition_opens_an_outage_and_recovery_closes_it(self, aws, prom_server):
        handler.render_handler({}, None)

        now = datetime.now(UTC).replace(tzinfo=None)
        down = mock_prometheus.responses_for("one-down", now)
        mock_prometheus.PrometheusHandler.responses = down
        result = handler.render_handler({}, None)
        assert result["overall"] == "partial_outage"
        tbl = store.table(TABLE)
        records = store.periods(tbl, store.OUTAGE, "mail-inbound")
        assert len(records) == 1
        assert records[0]["ended_at"] is None

        mock_prometheus.PrometheusHandler.responses = mock_prometheus.responses_for(
            "all-green", now
        )
        result = handler.render_handler({}, None)
        assert result["overall"] == "operational"
        records = store.periods(tbl, store.OUTAGE, "mail-inbound")
        assert records[0]["ended_at"] is not None
        assert records[0]["duration_seconds"] >= 0


class TestRecordHistory:
    def test_check_missing_from_metrics_writes_no_rollup(self, aws):
        tbl = store.table(TABLE)
        mani = handler.manifest()
        now = datetime.now(UTC)
        today = state.site_today(now, mani["site"]["timezone"])
        read = {
            "down_samples": {},
            "day_samples": {"website": 12.0},
            "day_successes": {"website": 11.0},
            "budget_samples": {},
        }
        handler.record_history(tbl, mani, None, read, now, today, {})
        day = today.isoformat()
        assert store.rollups(tbl, "website", day, day)[0]["samples"] == 12
        assert store.rollups(tbl, "api", day, day) == []

    def test_a_walk_inside_an_open_outage_opens_no_second_record(self, aws):
        """The walk resumes behind its watermark, so it re-reads samples an
        earlier run already judged. An outage longer than that lookback is
        re-read from inside itself, where the series carries no edge to
        stamp — and stamping one anyway writes a second record for the
        outage already open, which then counts its own overlap twice.

        The open record is what says the check was down. The snapshot's
        `up` comes from the instant query rather than from this walk, so it
        is the one thing here that can disagree with the record.
        """
        tbl = store.table(TABLE)
        mani = handler.manifest()
        now = datetime.now(UTC)
        today = state.site_today(now, mani["site"]["timezone"])
        started_at = state.iso(now - timedelta(minutes=90))
        store.open_period(tbl, store.OUTAGE, "api", started_at, 1)

        # Every sample failing, and a snapshot that still reads up.
        begin = now.timestamp() - 40 * 60
        read = {
            "down_samples": {"api": [(begin + i * 300, 0.0, 1.0) for i in range(9)]},
            "day_samples": {},
            "day_successes": {},
            "budget_samples": {},
        }
        previous = {"checks": {"api": {"up": True}}}

        opens = handler.open_periods(tbl, mani)
        handler.record_history(tbl, mani, previous, read, now, today, opens)

        records = store.periods(tbl, store.OUTAGE, "api")
        assert [r["started_at"] for r in records] == [started_at]

    def test_the_rollup_day_is_the_sites_not_utc(self):
        """22:30 UTC is already tomorrow in Amsterdam, and the bar the
        sample lands in has to agree with the clock on the page."""
        moment = datetime(2026, 8, 17, 22, 30, tzinfo=UTC)
        assert state.site_today(moment, "Europe/Amsterdam").isoformat() == "2026-08-18"


class TestSeriesStart:
    """How far back a run reads. The lookback is sized to fill the verdict
    window, which is not the same as reaching the edge of a run — an outage
    outlasts it, and then the walk begins inside one."""

    @staticmethod
    def mani():
        return handler.manifest()

    def test_it_resumes_behind_the_watermark(self):
        previous = {"processed_through": "2026-08-14T12:00:00Z"}
        now = datetime(2026, 8, 14, 12, 5, tzinfo=UTC)
        assert handler.series_start(self.mani(), previous, now, {}) == datetime(
            2026, 8, 14, 11, 20, tzinfo=UTC
        )

    def test_it_reaches_back_to_the_period_still_open(self):
        """A close is stamped at the first good sample the walk can see, so
        a walk that starts after the recovery reports the outage running
        longer than it did."""
        previous = {"processed_through": "2026-08-14T12:00:00Z"}
        now = datetime(2026, 8, 14, 12, 5, tzinfo=UTC)
        opens = {(store.OUTAGE, "api"): "2026-08-14T09:00:00Z"}
        assert handler.series_start(self.mani(), previous, now, opens) == datetime(
            2026, 8, 14, 9, 0, tzinfo=UTC
        )

    def test_a_recent_open_period_does_not_shorten_the_lookback(self):
        previous = {"processed_through": "2026-08-14T12:00:00Z"}
        now = datetime(2026, 8, 14, 12, 5, tzinfo=UTC)
        opens = {(store.OUTAGE, "api"): "2026-08-14T11:55:00Z"}
        assert handler.series_start(self.mani(), previous, now, opens) == datetime(
            2026, 8, 14, 11, 20, tzinfo=UTC
        )

    def test_nothing_reaches_past_the_horizon(self):
        """Prometheus keeps a fortnight; a period older than that is not
        walkable however long it has been open."""
        previous = {"processed_through": "2026-08-14T12:00:00Z"}
        now = datetime(2026, 8, 14, 12, 5, tzinfo=UTC)
        opens = {(store.OUTAGE, "api"): "2025-01-01T00:00:00Z"}
        assert handler.series_start(self.mani(), previous, now, opens) == now - timedelta(
            days=handler.SERIES_HORIZON_DAYS
        )

    def test_a_first_run_starts_at_the_horizon(self):
        now = datetime(2026, 8, 14, 12, 5, tzinfo=UTC)
        assert handler.series_start(self.mani(), None, now, {}) == now - timedelta(
            days=handler.SERIES_HORIZON_DAYS
        )


class TestDegraded:
    def test_prometheus_failure_renders_from_cache_and_writes_no_history(self, aws):
        handler.render_handler({}, None)
        tbl = store.table(TABLE)
        before = store.get_latest(tbl)
        mani = handler.manifest()
        day = state.site_today(datetime.now(UTC), mani["site"]["timezone"]).isoformat()
        before_rows = store.rollups(tbl, "website", day, day)

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
        mani = handler.manifest()
        day = state.site_today(datetime.now(UTC), mani["site"]["timezone"]).isoformat()
        # Untouched: a degraded run writes no history, and leaves the
        # watermark where it was so the gap is walked once metrics return.
        assert store.rollups(tbl, "website", day, day) == before_rows

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
