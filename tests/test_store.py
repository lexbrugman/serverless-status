import boto3
import pytest
import store
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
        store.put_latest(tbl, SNAPSHOT, "2026-08-14T11:59:00Z")
        loaded = store.get_latest(tbl)
        assert loaded["rendered_at"] == "2026-08-14T12:00:00Z"
        assert loaded["processed_through"] == "2026-08-14T11:59:00Z"
        assert loaded["checks"]["website"] == SNAPSHOT["checks"]["website"]

        assert isinstance(loaded["checks"]["website"]["latency_ms"], int)

    def test_a_run_that_read_nothing_records_no_watermark(self, tbl):
        """A degraded run leaves it where it was, so the gap it could not
        read is walked whole once Prometheus answers again."""
        store.put_latest(tbl, SNAPSHOT, None)
        assert store.get_latest(tbl)["processed_through"] is None


class TestRollups:
    def test_a_day_is_written_whole_and_rewriting_it_is_harmless(self, tbl):
        """Recomputed from the source rather than incremented, so a retry
        cannot double-count what it recalculates."""
        store.put_rollup(tbl, "website", "2026-08-14", 288, 287, 1)
        store.put_rollup(tbl, "website", "2026-08-14", 288, 287, 1)
        assert store.rollups(tbl, "website", "2026-08-14", "2026-08-14") == [
            {"date": "2026-08-14", "samples": 288, "successes": 287}
        ]

    def test_a_later_recount_replaces_the_earlier_one(self, tbl):
        store.put_rollup(tbl, "website", "2026-08-14", 100, 100, 1)
        store.put_rollup(tbl, "website", "2026-08-14", 120, 119, 1)
        rows = store.rollups(tbl, "website", "2026-08-14", "2026-08-14")
        assert rows[0]["samples"] == 120
        assert rows[0]["successes"] == 119

    def test_query_is_bounded_by_the_day_range(self, tbl):
        for day in ("2026-08-01", "2026-08-10", "2026-08-14"):
            store.put_rollup(tbl, "website", day, 10, 10, 1)
        rows = store.rollups(tbl, "website", "2026-08-09", "2026-08-14")
        assert [r["date"] for r in rows] == ["2026-08-10", "2026-08-14"]


class TestOutages:
    def test_open_then_close_derives_duration(self, tbl):
        store.open_period(tbl, store.OUTAGE, "mail", "2026-08-14T11:37:00Z", 1)
        store.close_period(tbl, store.OUTAGE, "mail", "2026-08-14T11:50:00Z")
        records = store.periods(tbl, store.OUTAGE, "mail")
        assert records == [
            {
                "started_at": "2026-08-14T11:37:00Z",
                "ended_at": "2026-08-14T11:50:00Z",
                "duration_seconds": 780,
            }
        ]

    def test_close_without_open_record_is_a_noop(self, tbl):
        store.close_period(tbl, store.OUTAGE, "mail", "2026-08-14T11:50:00Z")
        assert store.periods(tbl, store.OUTAGE, "mail") == []

    def test_close_skips_already_closed_records(self, tbl):
        store.open_period(tbl, store.OUTAGE, "mail", "2026-08-14T09:00:00Z", 1)
        store.close_period(tbl, store.OUTAGE, "mail", "2026-08-14T09:10:00Z")
        store.close_period(tbl, store.OUTAGE, "mail", "2026-08-14T11:50:00Z")
        records = store.periods(tbl, store.OUTAGE, "mail")
        assert len(records) == 1
        assert records[0]["duration_seconds"] == 600

    def test_the_two_kinds_of_period_do_not_collide(self, tbl):
        """One record shape under two prefixes: a degradation is not an
        outage, and neither read may see the other."""
        store.open_period(tbl, store.OUTAGE, "website", "2026-08-14T10:00:00Z", 1)
        store.open_period(tbl, store.DEGRADED, "website", "2026-08-14T11:00:00Z", 1)
        outages = store.periods(tbl, store.OUTAGE, "website")
        degraded = store.periods(tbl, store.DEGRADED, "website")
        assert [r["started_at"] for r in outages] == ["2026-08-14T10:00:00Z"]
        assert [r["started_at"] for r in degraded] == ["2026-08-14T11:00:00Z"]

    def test_closing_one_kind_leaves_the_other_open(self, tbl):
        store.open_period(tbl, store.OUTAGE, "website", "2026-08-14T10:00:00Z", 1)
        store.open_period(tbl, store.DEGRADED, "website", "2026-08-14T10:00:00Z", 1)
        store.close_period(tbl, store.DEGRADED, "website", "2026-08-14T10:30:00Z")
        assert store.periods(tbl, store.OUTAGE, "website")[0]["ended_at"] is None
        assert store.periods(tbl, store.DEGRADED, "website")[0]["duration_seconds"] == 1800

    def test_ongoing_outage_is_returned_open(self, tbl):
        store.open_period(tbl, store.OUTAGE, "mail", "2026-08-14T11:37:00Z", 1)
        records = store.periods(tbl, store.OUTAGE, "mail")
        assert records[0]["ended_at"] is None
        assert records[0]["duration_seconds"] is None


class TestPlain:
    def test_nested_structures_lose_their_decimals(self):
        from decimal import Decimal

        value = {"a": [Decimal("1"), Decimal("2.5")], "b": {"c": Decimal("3")}, "d": "x"}
        assert store._plain(value) == {"a": [1, 2.5], "b": {"c": 3}, "d": "x"}


class TestPagination:
    """A DynamoDB query returns at most 1 MB and a cursor for the rest.
    Stopping at the first page reads as a shorter history, not as an
    error — which is the failure a page about availability cannot afford."""

    class Paged:
        def __init__(self, pages):
            self.pages = pages
            self.seen = []

        def query(self, **kwargs):
            self.seen.append(kwargs.get("ExclusiveStartKey"))
            return self.pages[len(self.seen) - 1]

    def test_it_follows_the_cursor_to_the_end(self):
        tbl = self.Paged(
            [
                {"Items": [{"n": 1}], "LastEvaluatedKey": {"PK": "a"}},
                {"Items": [{"n": 2}], "LastEvaluatedKey": {"PK": "b"}},
                {"Items": [{"n": 3}]},
            ]
        )
        assert store._all_items(tbl, KeyConditionExpression="x") == [{"n": 1}, {"n": 2}, {"n": 3}]
        assert tbl.seen == [None, {"PK": "a"}, {"PK": "b"}]

    def test_a_single_page_asks_once(self):
        tbl = self.Paged([{"Items": [{"n": 1}]}])
        assert store._all_items(tbl, KeyConditionExpression="x") == [{"n": 1}]
        assert tbl.seen == [None]
