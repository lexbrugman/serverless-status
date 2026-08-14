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
