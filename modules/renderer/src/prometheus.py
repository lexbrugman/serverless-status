"""Prometheus query construction and response parsing; plain dicts out.

Probes run every 5-10 minutes, so the instant queries wrap the metric in
last_over_time over a window rather than sampling the instant — an instant
query would frequently return nothing.
"""

# The lookback window for "current" state.
WINDOW = "15m"

INSTANT_SUCCESS = f"max by (job) (last_over_time(probe_success[{WINDOW}]))"
INSTANT_DURATION = f"max by (job) (last_over_time(probe_duration_seconds[{WINDOW}]))"
RANGE_DURATION = "avg by (job) (probe_duration_seconds)"
RANGE_STEP_SECONDS = 900
RANGE_HOURS = 24


class PrometheusError(Exception):
    """Any failure to obtain a usable answer. The handler treats it as the
    degraded path, never as downtime."""


def _results(response: dict, expected_type: str) -> list[dict]:
    if response.get("status") != "success":
        raise PrometheusError(f"query status {response.get('status')!r}")
    data = response.get("data", {})
    if data.get("resultType") != expected_type:
        raise PrometheusError(f"expected {expected_type} result, got {data.get('resultType')!r}")
    return data.get("result", [])


def parse_vector(response: dict) -> dict[str, float]:
    """{job: value} out of an /api/v1/query response."""
    parsed = {}
    for series in _results(response, "vector"):
        job = series.get("metric", {}).get("job")
        if job is None:
            continue
        parsed[job] = float(series["value"][1])
    return parsed


def parse_matrix(response: dict) -> dict[str, list[tuple[float, float]]]:
    """{job: [(timestamp, value), ...]} out of an /api/v1/query_range response."""
    parsed = {}
    for series in _results(response, "matrix"):
        job = series.get("metric", {}).get("job")
        if job is None:
            continue
        parsed[job] = [(float(ts), float(value)) for ts, value in series.get("values", [])]
    return parsed
