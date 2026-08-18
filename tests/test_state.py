from datetime import UTC, date, datetime

import fixtures
import pytest
import state

NOW = datetime(2026, 8, 14, 12, 0, 0)


def manifest_with(**overrides):
    mani = fixtures.manifest()
    mani.update(overrides)
    return mani


class TestCheckState:
    def test_no_data_is_unknown(self):
        assert state.check_state(None, None, None) == "unknown"

    def test_failed_probe_is_down(self):
        assert state.check_state(False, 120, 800) == "down"

    def test_over_budget_is_slow(self):
        assert state.check_state(True, 900, 800) == "slow"

    def test_within_budget_is_up(self):
        assert state.check_state(True, 700, 800) == "up"

    def test_no_budget_is_never_slow(self):
        assert state.check_state(True, 99999, None) == "up"

    def test_no_latency_is_never_slow(self):
        assert state.check_state(True, None, 800) == "up"


class TestSiteToday:
    """The bars split days where the page's own clock says midnight is."""

    def test_the_day_is_the_sites_not_utc(self):
        # 22:30 UTC is already the next day in Amsterdam.
        moment = datetime(2026, 8, 17, 22, 30, tzinfo=UTC)
        assert state.site_today(moment, "Europe/Amsterdam").isoformat() == "2026-08-18"
        assert state.site_today(moment, "UTC").isoformat() == "2026-08-17"

    def test_a_naive_moment_is_read_as_utc(self):
        """The convention throughout the renderer, kept for callers that
        still hand one over."""
        naive = datetime(2026, 8, 17, 22, 30)
        assert state.site_today(naive, "Europe/Amsterdam").isoformat() == "2026-08-18"

    def test_it_holds_across_a_dst_change(self):
        # The Sunday Europe/Amsterdam falls back: 00:30 UTC is still 02:30
        # locally, the same day either side of the change.
        before = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
        after = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
        assert state.site_today(before, "Europe/Amsterdam").isoformat() == "2026-10-25"
        assert state.site_today(after, "Europe/Amsterdam").isoformat() == "2026-10-25"

    def test_an_unknown_zone_is_an_error_not_a_silent_utc(self):
        with pytest.raises((KeyError, ValueError)):
            state.site_today(datetime(2026, 8, 17, tzinfo=UTC), "Nowhere/Nowhere")


class TestOverallState:
    def test_all_unknown(self):
        assert state.overall_state(["unknown", "unknown"]) == "unknown"

    def test_empty(self):
        assert state.overall_state([]) == "unknown"

    def test_all_known_down(self):
        assert state.overall_state(["down", "down", "unknown"]) == "major_outage"

    def test_some_down(self):
        assert state.overall_state(["up", "down"]) == "partial_outage"

    def test_a_check_nobody_hears_from_is_not_operational(self):
        assert state.overall_state(["up", "up", "unknown"]) == "partial_unknown"

    def test_a_real_fault_outranks_silence(self):
        assert state.overall_state(["up", "slow", "unknown"]) == "degraded"
        assert state.overall_state(["up", "down", "unknown"]) == "partial_outage"

    def test_all_known_and_healthy_is_operational(self):
        assert state.overall_state(["up", "up"]) == "operational"

    def test_slow_degrades(self):
        assert state.overall_state(["up", "slow"]) == "degraded"

    def test_all_up(self):
        assert state.overall_state(["up", "up"]) == "operational"


class TestAddress:
    def test_https_default_port_with_path(self):
        check = {"type": "https", "host": "api.example.com", "port": 443, "path": "/health"}
        assert state.address(check) == "api.example.com/health"

    def test_https_root_path_is_bare(self):
        check = {"type": "https", "host": "www.example.com", "port": 443, "path": "/"}
        assert state.address(check) == "www.example.com"

    def test_http_nondefault_port(self):
        check = {"type": "http", "host": "www.example.com", "port": 8080, "path": None}
        assert state.address(check) == "www.example.com:8080"

    def test_smtp_hides_its_default_port(self):
        check = {"type": "smtp", "host": "mx1.example.com", "port": 25, "path": None}
        assert state.address(check) == "mx1.example.com"

    def test_smtp_shows_a_submission_port(self):
        check = {"type": "smtp", "host": "mx1.example.com", "port": 587, "path": None}
        assert state.address(check) == "mx1.example.com:587"

    def test_ping_is_host_only(self):
        check = {"type": "ping", "host": "gw.example.com", "port": None, "path": None}
        assert state.address(check) == "gw.example.com"


class TestSubtitle:
    """The protocol is shown as its own tag, so the subtitle carries only
    what the display name does not already say."""

    def test_empty_when_the_name_is_the_address(self):
        check = {
            "type": "ping",
            "host": "gw.example.com",
            "port": None,
            "path": None,
            "display": "gw.example.com",
        }
        assert state.subtitle(check) == ""

    def test_keeps_only_the_remainder(self):
        check = {
            "type": "https",
            "host": "api.example.com",
            "port": 443,
            "path": "/health",
            "display": "api.example.com",
        }
        assert state.subtitle(check) == "/health"

    def test_only_a_nondefault_port_survives_a_hostname_display(self):
        check = {
            "type": "smtp",
            "host": "mx1.example.com",
            "port": 587,
            "path": None,
            "display": "mx1.example.com",
        }
        assert state.subtitle(check) == ":587"

    def test_default_port_leaves_nothing_to_show(self):
        check = {
            "type": "smtp",
            "host": "mx1.example.com",
            "port": 25,
            "path": None,
            "display": "mx1.example.com",
        }
        assert state.subtitle(check) == ""

    def test_unrelated_display_keeps_the_whole_address(self):
        check = {
            "type": "https",
            "host": "www.example.com",
            "port": 443,
            "path": None,
            "display": "Website",
        }
        assert state.subtitle(check) == "www.example.com"


class TestDaySeries:
    def test_missing_and_empty_days_have_no_ratio(self):
        rows = [
            {"date": "2026-08-14", "samples": 100, "successes": 99},
            {"date": "2026-08-13", "samples": 0, "successes": 0},
        ]
        days = state.day_series(rows, 3, date(2026, 8, 14))
        assert [d["ratio"] for d in days] == [None, None, 0.99]
        assert days[0]["date"] == "2026-08-12"

    def test_window_ratio_is_sample_weighted(self):
        rows = [
            {"date": "2026-08-13", "samples": 300, "successes": 300},
            {"date": "2026-08-14", "samples": 100, "successes": 0},
            {"date": "2026-01-01", "samples": 100, "successes": 0},
        ]
        days = state.day_series(rows, 2, date(2026, 8, 14))
        assert state.window_ratio(days, rows) == 300 / 400

    def test_window_ratio_without_samples_is_none(self):
        assert state.window_ratio([{"date": "2026-08-14"}], []) is None


class TestConfirmedTransitions:
    """Edges read out of the series, at the sample they actually happened."""

    @staticmethod
    def series(values, step=300):
        return [(float(i * step), float(v)) for i, v in enumerate(values)]

    def test_an_outage_is_stamped_at_its_first_failing_sample(self):
        # Confirmed on the third failure; it began on the first.
        result = state.confirmed_transitions(self.series([1, 1, 0, 0, 0]), 3, 0.5, True)
        assert result == [{"kind": "opened", "at": "1970-01-01T00:10:00Z"}]

    def test_recovery_closes_at_the_first_good_sample(self):
        result = state.confirmed_transitions(self.series([0, 0, 0, 1, 1, 1]), 3, 0.5, False)
        assert result == [{"kind": "closed", "at": "1970-01-01T00:15:00Z"}]

    def test_a_single_failure_is_not_an_outage(self):
        assert state.confirmed_transitions(self.series([1, 1, 0, 1, 1]), 3, 0.5, True) == []

    def test_an_unknown_starting_point_is_no_transition(self):
        """Absence of data is never downtime, on either side."""
        assert state.confirmed_transitions(self.series([0, 0, 0]), 3, 0.5, None) == []

    def test_too_few_samples_to_judge_yields_nothing(self):
        assert state.confirmed_transitions(self.series([0]), 3, 0.5, True) == []

    def test_a_quorum_absorbs_one_unhappy_probe_location(self):
        """Two of three locations reporting success is still up at 0.5."""
        two_thirds = [1.0, 1.0, 2 / 3, 2 / 3, 2 / 3]
        assert state.confirmed_transitions(self.series(two_thirds), 3, 0.5, True) == []

    def test_an_empty_series_is_no_transition(self):
        assert state.confirmed_transitions([], 3, 0.5, True) == []


class TestAssemble:
    def test_one_down_fixture(self):
        built = fixtures.build_state("one-down", NOW)
        by_key = {c["key"]: c for c in built["checks"]}
        assert by_key["mail-inbound"]["state"] == "down"
        assert by_key["mail-inbound"]["latency_ms"] is None
        assert by_key["website"]["state"] == "up"
        assert built["overall"] == "partial_outage"
        assert built["source"] == "grafana"
        assert built["outages"][0]["key"] == "mail-inbound"
        assert built["outages"][0]["ended_at"] is None

    def test_slow_fixture_degrades_the_banner(self):
        built = fixtures.build_state("degraded-slow", NOW)
        by_key = {c["key"]: c for c in built["checks"]}
        assert by_key["api"]["state"] == "slow"
        assert built["overall"] == "degraded"

    def test_stale_cache_renders_from_snapshot(self):
        built = fixtures.build_state("stale-cache", NOW)
        assert built["degraded"] is True
        assert built["source"] == "cache"
        assert built["cached_at"] == "2026-08-14T11:13:00Z"
        states = {c["state"] for c in built["checks"]}
        assert states == {"up"}
        assert all(c["spark"] is None for c in built["checks"])

    def test_degraded_without_snapshot_is_unknown(self):
        built = state.assemble(fixtures.manifest(), now=NOW, degraded=True)
        assert built["overall"] == "unknown"
        assert {c["state"] for c in built["checks"]} == {"unknown"}
        assert all(c["since"] is None for c in built["checks"])

    def test_missing_job_in_metrics_is_unknown(self):
        built = state.assemble(
            fixtures.manifest(), now=NOW, success={"website": 1.0}, duration={"website": 0.1}
        )
        by_key = {c["key"]: c for c in built["checks"]}
        assert by_key["website"]["state"] == "up"
        assert by_key["api"]["state"] == "unknown"

    def test_since_is_kept_across_unchanged_state(self):
        previous = {
            "rendered_at": "2026-08-14T11:59:00Z",
            "checks": {"website": {"up": True, "latency_ms": 100, "since": "2026-07-01T00:00:00Z"}},
        }
        built = state.assemble(
            fixtures.manifest(),
            now=NOW,
            success={"website": 1.0, "api": 0.0},
            duration={"website": 0.1},
            previous=previous,
        )
        by_key = {c["key"]: c for c in built["checks"]}
        assert by_key["website"]["since"] == "2026-07-01T00:00:00Z"
        assert by_key["api"]["since"] == "2026-08-14T12:00:00Z"

    def test_spark_preserves_gaps(self):
        built = state.assemble(
            fixtures.manifest(),
            now=NOW,
            success={"website": 1.0},
            duration_range={"website": [(1.0, 0.2), (2.0, None)]},
        )
        by_key = {c["key"]: c for c in built["checks"]}
        assert by_key["website"]["spark"] == [200.0, None]

    def test_outages_outside_log_window_are_dropped(self):
        outages = {
            "website": [
                {
                    "started_at": "2026-05-01T00:00:00Z",
                    "ended_at": "2026-05-01T01:00:00Z",
                    "duration_seconds": 3600,
                }
            ]
        }
        built = state.assemble(fixtures.manifest(), now=NOW, outages=outages)
        assert built["outages"] == []

    def test_groups_derive_from_member_orders(self):
        built = fixtures.build_state("all-green", NOW)
        assert [g["name"] for g in built["groups"]] == ["Web", "Mail", "Network"]
        assert [c["key"] for c in built["groups"][0]["checks"]] == ["website", "api", "docs"]

    def test_order_defaults_when_absent(self):
        mani = fixtures.manifest()
        for check in mani["checks"].values():
            del check["order"]
        built = state.assemble(mani, now=NOW)
        assert [g["name"] for g in built["groups"]] == ["Mail", "Network", "Web"]
        assert [c["key"] for c in built["groups"][2]["checks"]] == ["api", "docs", "website"]


class TestGroupOrder:
    def test_lowest_member_order_wins_then_name(self):
        checks = {
            "a": {"group": "Zeta", "order": 5},
            "b": {"group": "Alpha", "order": 10},
            "c": {"group": "Zeta", "order": 90},
            "d": {"group": "Mid", "order": 10},
        }
        assert state.group_order(checks) == ["Zeta", "Alpha", "Mid"]

    def test_missing_order_counts_as_default(self):
        checks = {
            "a": {"group": "Later", "order": 60},
            "b": {"group": "Default"},
        }
        assert state.group_order(checks) == ["Default", "Later"]


class TestSnapshot:
    def test_snapshot_round_trips_the_next_render(self):
        built = fixtures.build_state("one-down", NOW)
        snap = state.snapshot(built)
        assert snap["rendered_at"] == "2026-08-14T12:00:00Z"
        assert snap["checks"]["mail-inbound"]["up"] is False
        assert snap["checks"]["website"]["up"] is True
        assert set(snap["checks"]) == set(fixtures.manifest()["checks"])
