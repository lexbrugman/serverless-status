import boto3
import pytest
import store
from botocore.exceptions import ClientError
from moto import mock_aws

TABLE = "status-test"


@pytest.fixture
def tbl():
    with mock_aws():
        client = boto3.client("dynamodb")
        client.create_table(
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
        yield store.table(TABLE)


SNAPSHOT = {
    "rendered_at": "2026-08-14T12:00:00Z",
    "checks": {
        "website": {"up": True, "latency_ms": 142, "since": "2026-07-01T00:00:00Z"},
        "mail": {"up": False, "latency_ms": None, "since": "2026-08-14T11:37:00Z"},
    },
}


class TestLatest:
    def test_empty_table_has_no_snapshot(self, tbl):
        assert store.get_latest(tbl) is None

    def test_round_trip_restores_plain_types(self, tbl):
        store.put_latest(tbl, SNAPSHOT, source="grafana", degraded=False)
        loaded = store.get_latest(tbl)
        assert loaded["rendered_at"] == "2026-08-14T12:00:00Z"
        assert loaded["source"] == "grafana"
        assert loaded["degraded"] is False
        assert loaded["checks"]["website"] == SNAPSHOT["checks"]["website"]
        assert isinstance(loaded["checks"]["website"]["latency_ms"], int)


class TestRollups:
    def test_samples_accumulate_atomically(self, tbl):
        store.update_rollup(tbl, "website", "2026-08-14", True, 100, 1)
        store.update_rollup(tbl, "website", "2026-08-14", True, 300, 1)
        store.update_rollup(tbl, "website", "2026-08-14", False, None, 1)
        rows = store.rollups(tbl, "website", "2026-08-14", "2026-08-14")
        assert rows == [
            {
                "date": "2026-08-14",
                "samples": 3,
                "successes": 2,
                "latency_sum": 400,
                "latency_max": 300,
            }
        ]

    def test_latency_max_only_rises(self, tbl):
        store.update_rollup(tbl, "website", "2026-08-14", True, 300, 1)
        store.update_rollup(tbl, "website", "2026-08-14", True, 100, 1)
        rows = store.rollups(tbl, "website", "2026-08-14", "2026-08-14")
        assert rows[0]["latency_max"] == 300

    def test_query_is_bounded_by_the_day_range(self, tbl):
        for day in ("2026-08-01", "2026-08-10", "2026-08-14"):
            store.update_rollup(tbl, "website", day, True, 100, 1)
        rows = store.rollups(tbl, "website", "2026-08-09", "2026-08-14")
        assert [r["date"] for r in rows] == ["2026-08-10", "2026-08-14"]

    def test_unexpected_client_error_propagates(self, tbl):
        class Exploding:
            calls = 0

            def update_item(self, **kwargs):
                Exploding.calls += 1
                if Exploding.calls > 1:
                    raise ClientError(
                        {"Error": {"Code": "ValidationException", "Message": "boom"}},
                        "UpdateItem",
                    )

        with pytest.raises(ClientError, match="ValidationException"):
            store.update_rollup(Exploding(), "website", "2026-08-14", True, 100, 1)


class TestOutages:
    def test_open_then_close_derives_duration(self, tbl):
        store.open_outage(tbl, "mail", "2026-08-14T11:37:00Z", 1)
        store.close_outage(tbl, "mail", "2026-08-14T11:50:00Z")
        records = store.outages(tbl, "mail")
        assert records == [
            {
                "started_at": "2026-08-14T11:37:00Z",
                "ended_at": "2026-08-14T11:50:00Z",
                "duration_seconds": 780,
            }
        ]

    def test_close_without_open_record_is_a_noop(self, tbl):
        store.close_outage(tbl, "mail", "2026-08-14T11:50:00Z")
        assert store.outages(tbl, "mail") == []

    def test_close_skips_already_closed_records(self, tbl):
        store.open_outage(tbl, "mail", "2026-08-14T09:00:00Z", 1)
        store.close_outage(tbl, "mail", "2026-08-14T09:10:00Z")
        store.close_outage(tbl, "mail", "2026-08-14T11:50:00Z")
        records = store.outages(tbl, "mail")
        assert len(records) == 1
        assert records[0]["duration_seconds"] == 600

    def test_ongoing_outage_is_returned_open(self, tbl):
        store.open_outage(tbl, "mail", "2026-08-14T11:37:00Z", 1)
        records = store.outages(tbl, "mail")
        assert records[0]["ended_at"] is None
        assert records[0]["duration_seconds"] is None


class TestPlain:
    def test_nested_structures_lose_their_decimals(self):
        from decimal import Decimal

        value = {"a": [Decimal("1"), Decimal("2.5")], "b": {"c": Decimal("3")}, "d": "x"}
        assert store._plain(value) == {"a": [1, 2.5], "b": {"c": 3}, "d": "x"}
