from datetime import UTC, datetime

import prometheus
import pytest


def vector(job_values):
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": metric, "value": [1755172800.0, value]} for metric, value in job_values
            ],
        },
    }


class TestParseVector:
    def test_values_by_job(self):
        response = vector([({"job": "website"}, "1"), ({"job": "api"}, "0")])
        assert prometheus.parse_vector(response) == {"website": 1.0, "api": 0.0}

    def test_series_without_job_label_is_skipped(self):
        response = vector([({}, "1"), ({"job": "api"}, "1")])
        assert prometheus.parse_vector(response) == {"api": 1.0}

    def test_error_status_raises(self):
        with pytest.raises(prometheus.PrometheusError, match="status 'error'"):
            prometheus.parse_vector({"status": "error"})

    def test_wrong_result_type_raises(self):
        response = {"status": "success", "data": {"resultType": "matrix", "result": []}}
        with pytest.raises(prometheus.PrometheusError, match="expected vector"):
            prometheus.parse_vector(response)


class TestParseMatrix:
    def test_points_by_job(self):
        response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {"metric": {"job": "website"}, "values": [[1.0, "0.2"], [2.0, "0.3"]]},
                    {"metric": {}, "values": [[1.0, "0.9"]]},
                ],
            },
        }
        assert prometheus.parse_matrix(response) == {"website": [(1.0, 0.2), (2.0, 0.3)]}

    def test_wrong_result_type_raises(self):
        response = {"status": "success", "data": {"resultType": "vector", "result": []}}
        with pytest.raises(prometheus.PrometheusError, match="expected matrix"):
            prometheus.parse_matrix(response)


class TestDurationQuery:
    """The most recent reading, over the window the verdict beside it was
    made over — so the latency a row prints and the state it prints describe
    the same stretch of time. A fixed window is a guess about how often the
    probe runs, and a check slower than the guess shows no latency at all."""

    def test_it_matches_its_pinned_literal(self):
        assert prometheus.duration_query(["website", "api"], 5, 3) == (
            'avg by (job) (last_over_time(probe_duration_seconds{job=~"^(api|website)$"}[15m]))'
        )

    def test_the_window_follows_the_probe_interval(self):
        assert "[30m]" in prometheus.duration_query(["dns"], 10, 3)
        assert "[180m]" in prometheus.duration_query(["dns"], 60, 3)

    def test_it_asks_only_about_the_jobs_it_was_given(self):
        """Unselected, it reads every probe in the account — including
        checks that belong to no page this renderer speaks for."""
        assert 'job=~"^(dns)$"' in prometheus.duration_query(["dns"], 10, 3)


class TestRangeGrid:
    """query_range places its samples at start + k*step, so a start that
    moves between runs moves every sample with it. A period is keyed by the
    moment it began, so a grid that shifts hands the same outage a different
    key each run — and the record it should have matched is not there."""

    @staticmethod
    def captured(monkeypatch) -> dict:
        seen: dict = {}

        def request(credentials, path, params):
            seen.update(params)
            return {"status": "success", "data": {"resultType": "matrix", "result": []}}

        monkeypatch.setattr(prometheus, "_request", request)
        return seen

    def test_the_start_is_anchored_to_a_multiple_of_the_step(self, monkeypatch):
        seen = self.captured(monkeypatch)
        prometheus.series(
            {}, "q", datetime(2026, 8, 14, 12, 3, 17), datetime(2026, 8, 14, 12, 30), 300
        )
        assert seen["start"] % 300 == 0

    def test_starts_within_one_step_share_a_grid(self, monkeypatch):
        """Consecutive runs resume from different watermarks; the samples
        they read must still carry the same timestamps."""
        end = datetime(2026, 8, 14, 12, 30)
        seen = self.captured(monkeypatch)
        prometheus.series({}, "q", datetime(2026, 8, 14, 11, 41, 9), end, 300)
        first = seen["start"]
        prometheus.series({}, "q", datetime(2026, 8, 14, 11, 44, 52), end, 300)
        assert seen["start"] == first

    def test_the_anchor_never_moves_the_start_later(self, monkeypatch):
        """Rounding forward would drop the very sample the caller reached
        back for."""
        seen = self.captured(monkeypatch)
        start = datetime(2026, 8, 14, 12, 3, 17)
        prometheus.series({}, "q", start, datetime(2026, 8, 14, 12, 30), 300)
        assert seen["start"] <= start.replace(tzinfo=UTC).timestamp()


class TestUpQuery:
    """Pinned against modules/alerting, which builds the identical string.
    The page and the pager answer to one definition of down, or they will
    eventually tell different stories about the same check."""

    EXPECTED = (
        '(sum by (job) (sum_over_time(probe_success{job=~"^(api-example-com-https'
        '|mx1-example-com-smtp)$"}[15m]))'
        ' / sum by (job) (count_over_time(probe_success{job=~"^(api-example-com-https'
        '|mx1-example-com-smtp)$"}[15m]))'
        " >= bool 0.5) and "
        '(sum by (job) (count_over_time(probe_success{job=~"^(api-example-com-https'
        '|mx1-example-com-smtp)$"}[15m])) >= 2)'
    )

    def test_matches_its_pinned_literal(self):
        """This pins the renderer's half only. What ties it to the alert
        rule is scripts/check-cross-layer.py, which compares this literal to
        the one the rule's own test states."""
        query = prometheus.up_query(["mx1-example-com-smtp", "api-example-com-https"], 5, 3, 0.5)
        assert query == self.EXPECTED

    def test_the_window_is_a_multiple_of_the_probe_interval(self):
        assert "[30m]" in prometheus.up_query(["a"], 10, 3, 0.5)

    def test_bool_keeps_down_distinguishable_from_absent(self):
        """Without it the comparison filters, and a failing check looks the
        same as one nobody heard from."""
        assert ">= bool " in prometheus.up_query(["a"], 5, 2, 0.5)

    def test_one_late_probe_is_tolerated(self):
        assert prometheus.up_query(["a"], 5, 2, 0.5).endswith(">= 1)")
        assert prometheus.up_query(["a"], 5, 4, 0.5).endswith(">= 3)")
