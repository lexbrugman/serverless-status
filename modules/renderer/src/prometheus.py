"""Prometheus query construction, HTTP, and response parsing; plain dicts out.

Probes run every 5-10 minutes, so the instant queries wrap the metric in
last_over_time over a window rather than sampling the instant — an instant
query would frequently return nothing. HTTP is urllib on purpose: the
handler ships as stdlib plus boto3, nothing to package.
"""

import base64
import http.client
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

# Averaged across probe locations, matching the instant query beside it: one
# location's reading is not the page's subject, and the instant number and
# the sparkline are the same quantity at two resolutions.
RANGE_DURATION = "avg by (job) (probe_duration_seconds)"
RANGE_STEP_SECONDS = 900
RANGE_HOURS = 24


def _selector(jobs: list[str]) -> str:
    """The label matcher every query selects its jobs with, written once so
    two queries cannot come to disagree about which checks they cover."""
    return f'{{job=~"^({"|".join(sorted(jobs))})$"}}'


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
    selector = f"probe_success{_selector(jobs)}"
    ratio = (
        f"sum by (job) (sum_over_time({selector}[{window}m]))"
        f" / sum by (job) (count_over_time({selector}[{window}m]))"
    )
    enough = f"sum by (job) (count_over_time({selector}[{window}m])) >= {min_samples}"
    return f"({ratio} >= bool {quorum}) and ({enough})"


def duration_query(jobs: list[str], frequency_minutes: int, window_multiple: int) -> str:
    """The most recent latency reading per job.

    The last value rather than a verdict over time — but read over the same
    window the verdict beside it was made over, so the number a row prints
    and the state it prints describe one stretch of time. A fixed window
    would be a guess about how often the probe runs, and a check slower than
    the guess has nothing in it: the page would show no latency at all, and
    nothing would say why.
    """
    return (
        "avg by (job) (last_over_time("
        f"probe_duration_seconds{_selector(jobs)}[{frequency_minutes * window_multiple}m]))"
    )


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
    # HTTPException covers the responses that arrive malformed rather than
    # not at all — an IncompleteRead is neither an OSError nor a ValueError,
    # and one escaping here would crash the invocation instead of rendering
    # the degraded page this class exists to reach.
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise PrometheusError(f"{path}: {error}") from error


# Both sides of a ratio rather than the ratio: the verdict pools them over
# its window, which is what up_query and the alert rule compute. Dividing
# per instant and averaging afterwards weights every instant equally, and
# the two part company whenever the number of reporting locations varies.
SUCCESS_COUNTS = (
    "sum by (job) (probe_success{selector})",
    "count by (job) (probe_success{selector})",
)

BUDGET_COUNTS = (
    "sum by (job) (probe_duration_seconds{selector} <= bool {budget})",
    "count by (job) (probe_duration_seconds{selector})",
)


def budget_counts_queries(jobs: list[str], budget_seconds: float) -> tuple[str, str]:
    """(locations meeting the budget, locations reporting) per instant.

    A dissenting minority of locations must not read as degradation, and a
    mean cannot filter a minority — only a quorum can. So the counts are
    taken per instant here and the verdict applied over a window of them in
    the renderer, which is the shape the success counts and the incident log
    already have.

    `bool` is load-bearing for the same reason it is in up_query: without it
    the comparison filters, and a location that is slow becomes
    indistinguishable from one nobody heard from.
    """
    selector = _selector(jobs)
    return tuple(part.format(selector=selector, budget=budget_seconds) for part in BUDGET_COUNTS)


def success_counts_queries(jobs: list[str]) -> tuple[str, str]:
    """(locations succeeding, locations reporting) per instant. The verdict
    window is applied over these in the renderer rather than in PromQL,
    because an incident is timestamped from the first failing sample and a
    windowed expression has already lost it."""
    selector = _selector(jobs)
    return tuple(part.format(selector=selector) for part in SUCCESS_COUNTS)


def day_totals_queries(jobs: list[str], elapsed_seconds: int) -> tuple[str, str]:
    """(executions, successes) so far in the day, for the rollup. Recomputed
    from the source rather than incremented, so a retry cannot double-count
    what it recalculates."""
    selector = f"probe_success{_selector(jobs)}"
    window = f"[{elapsed_seconds}s]"
    return (
        f"sum by (job) (count_over_time({selector}{window}))",
        f"sum by (job) (sum_over_time({selector}{window}))",
    )


def anchored(start: datetime, step: int) -> float:
    """The grid point at or before `start`.

    query_range places its samples at start + k*step, so a start that moves
    between runs moves every sample with it. Runs resume from wherever the
    last one stopped reading, which is not a whole number of steps away, so
    without an anchor one check's samples carry different timestamps every
    run. A period is keyed by the moment it began, and a key that moves is
    a record the next run cannot find.

    Backwards, never forwards: rounding up would drop the very sample the
    caller reached back for.
    """
    return _epoch(start) // step * step


def series(credentials: dict, query: str, start: datetime, end: datetime, step: int) -> dict:
    """A range query at an explicit step, for walking samples over time."""
    response = _request(
        credentials,
        "/api/v1/query_range",
        {"query": query, "start": anchored(start, step), "end": _epoch(end), "step": step},
    )
    return parse_matrix(response)


def paired_series(
    credentials: dict, queries: tuple[str, str], start: datetime, end: datetime, step: int
) -> dict[str, list[tuple[float, float, float]]]:
    """Both sides of one ratio over the same range, zipped per instant."""
    return paired(*(series(credentials, query, start, end, step) for query in queries))


def instant(credentials: dict, query: str, now: datetime) -> dict[str, float]:
    response = _request(credentials, "/api/v1/query", {"query": query, "time": _epoch(now)})
    return parse_vector(response)


def on_grid(
    points: list[tuple[float, float]], start: float, end: float, step: int
) -> list[tuple[float, float | None]]:
    """The series placed on the grid it was asked for, gaps included.

    Prometheus omits the instants it has no sample for, so a returned series
    is dense however much of the window went unobserved. The sparkline
    positions by index, which draws that omission as time that passed
    normally — a probe that stopped for six hours reads as a steady line.
    Padding the holes is what lets the shape stay honest about them.
    """
    sampled = {round((ts - start) / step): value for ts, value in points}
    return [
        (start + slot * step, sampled.get(slot)) for slot in range(int((end - start) // step) + 1)
    ]


def latency_range(credentials: dict, now: datetime) -> dict[str, list[tuple[float, float | None]]]:
    start = _epoch(now - timedelta(hours=RANGE_HOURS))
    end = _epoch(now)
    response = _request(
        credentials,
        "/api/v1/query_range",
        {
            "query": RANGE_DURATION,
            "start": start,
            "end": end,
            "step": RANGE_STEP_SECONDS,
        },
    )
    return {
        job: on_grid(points, start, end, RANGE_STEP_SECONDS)
        for job, points in parse_matrix(response).items()
    }


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


def paired(numerators: dict, denominators: dict) -> dict[str, list[tuple[float, float, float]]]:
    """Two range results zipped on their timestamps, as (at, met, of).

    An instant present on only one side is dropped: half a sample is not a
    sample, and a numerator without its denominator has no ratio to pool.
    """
    merged = {}
    for job, points in numerators.items():
        against = dict(denominators.get(job, []))
        merged[job] = [(at, value, against[at]) for at, value in points if at in against]
    return merged


def parse_matrix(response: dict) -> dict[str, list[tuple[float, float]]]:
    """{job: [(timestamp, value), ...]} out of an /api/v1/query_range response."""
    parsed = {}
    for series in _results(response, "matrix"):
        job = series.get("metric", {}).get("job")
        if job is None:
            continue
        parsed[job] = [(float(ts), float(value)) for ts, value in series.get("values", [])]
    return parsed
