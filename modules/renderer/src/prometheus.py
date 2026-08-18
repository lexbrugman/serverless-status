"""Prometheus query construction, HTTP, and response parsing; plain dicts out.

Probes run every 5-10 minutes, so the instant queries wrap the metric in
last_over_time over a window rather than sampling the instant — an instant
query would frequently return nothing. HTTP is urllib on purpose: the
handler ships as stdlib plus boto3, nothing to package.
"""

import base64
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

# The lookback window for the latency reading, which wants the most recent
# value rather than a verdict over time.
WINDOW = "15m"

INSTANT_DURATION = f"max by (job) (last_over_time(probe_duration_seconds[{WINDOW}]))"
RANGE_DURATION = "avg by (job) (probe_duration_seconds)"
RANGE_STEP_SECONDS = 900
RANGE_HOURS = 24


def up_query(jobs: list[str], frequency_minutes: int, window_multiple: int, quorum: float) -> str:
    """The one definition of up, shared with the alert rule.

    The share of probe executions in the window that succeeded, against a
    quorum — so a single failed probe is not an outage, and one unhappy
    probe location out of several is not either. Counting executions rather
    than evaluations is what makes it a debounce: a pending period shorter
    than the probe interval only delays, it never requires a second
    failure.

    `bool` is load-bearing. Without it a comparison filters rather than
    returning 0, and a check that is down becomes indistinguishable from
    one nobody heard from. The trailing `and` drops a job with too few
    samples to judge, which leaves it unknown rather than guessing.
    """
    window = frequency_minutes * window_multiple
    # One late probe is tolerated; below that there is not enough in the
    # window to judge, and guessing is what a debounce exists to avoid.
    min_samples = max(1, window_multiple - 1)
    selector = f'probe_success{{job=~"^({"|".join(sorted(jobs))})$"}}'
    ratio = (
        f"sum by (job) (sum_over_time({selector}[{window}m]))"
        f" / sum by (job) (count_over_time({selector}[{window}m]))"
    )
    enough = f"sum by (job) (count_over_time({selector}[{window}m])) >= {min_samples}"
    return f"({ratio} >= bool {quorum}) and ({enough})"


class PrometheusError(Exception):
    """Any failure to obtain a usable answer. The handler treats it as the
    degraded path, never as downtime."""


def _epoch(moment: datetime) -> float:
    """Naive datetimes are UTC by convention throughout the renderer."""
    return moment.replace(tzinfo=UTC).timestamp()


def _request(credentials: dict, path: str, params: dict) -> dict:
    url = f"{credentials['query_url']}{path}?{urllib.parse.urlencode(params)}"
    basic = base64.b64encode(f"{credentials['user']}:{credentials['token']}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError) as error:
        raise PrometheusError(f"{path}: {error}") from error


SUCCESS_FRACTION = (
    "sum by (job) (probe_success{selector}) / count by (job) (probe_success{selector})"
)


def fraction_query(jobs: list[str]) -> str:
    """The share of probe locations reporting success, per instant. The
    verdict window is applied over these in the renderer rather than in
    PromQL, because an incident is timestamped from the first failing
    sample and a windowed expression has already lost it."""
    selector = f'{{job=~"^({"|".join(sorted(jobs))})$"}}'
    return SUCCESS_FRACTION.format(selector=selector)


def day_totals_queries(jobs: list[str], elapsed_seconds: int) -> tuple[str, str]:
    """(executions, successes) so far in the day, for the rollup. Recomputed
    from the source rather than incremented, so a retry cannot double-count
    what it recalculates."""
    selector = f'probe_success{{job=~"^({"|".join(sorted(jobs))})$"}}'
    window = f"[{elapsed_seconds}s]"
    return (
        f"sum by (job) (count_over_time({selector}{window}))",
        f"sum by (job) (sum_over_time({selector}{window}))",
    )


def series(credentials: dict, query: str, start: datetime, end: datetime, step: int) -> dict:
    """A range query at an explicit step, for walking samples over time."""
    response = _request(
        credentials,
        "/api/v1/query_range",
        {"query": query, "start": _epoch(start), "end": _epoch(end), "step": step},
    )
    return parse_matrix(response)


def instant(credentials: dict, query: str, now: datetime) -> dict[str, float]:
    response = _request(credentials, "/api/v1/query", {"query": query, "time": _epoch(now)})
    return parse_vector(response)


def latency_range(credentials: dict, now: datetime) -> dict[str, list[tuple[float, float]]]:
    response = _request(
        credentials,
        "/api/v1/query_range",
        {
            "query": RANGE_DURATION,
            "start": _epoch(now - timedelta(hours=RANGE_HOURS)),
            "end": _epoch(now),
            "step": RANGE_STEP_SECONDS,
        },
    )
    return parse_matrix(response)


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
