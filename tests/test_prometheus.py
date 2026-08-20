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
