"""The Lambda entry point — orchestration only, no decisions.

Every decision lives in state/render/badge/theme (pure) or store/prometheus
(one I/O concern each); this file just wires the flow: query, detect, fold,
read, assemble, render, publish.
"""

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import badge
import prometheus
import render
import report
import state
import store

# Warm invocations reuse the manifest and the SSM-fetched credentials.
_cache: dict = {}

# The manifest ships inside the deployment zip, next to this file; the test
# suite and the dev stack point elsewhere.
MANIFEST_PATH = os.environ.get("MANIFEST_PATH", str(Path(__file__).parent / "manifest.json"))

OBJECTS = {
    "index.html": "text/html; charset=utf-8",
    "status.json": "application/json",
    "badge.svg": "image/svg+xml",
}
CACHE_CONTROL = "public, max-age=30"


def manifest() -> dict:
    if "manifest" not in _cache:
        _cache["manifest"] = json.loads(Path(MANIFEST_PATH).read_text())
    return _cache["manifest"]


def prometheus_sources() -> list[dict]:
    """From SSM in production; from PROM_ENDPOINT in the local dev stack,
    which has no SSM. One source per Grafana account feeding the page.
    Nothing being set is a configuration failure, reported through the
    degraded path rather than a crash."""
    if "sources" not in _cache:
        parameter = os.environ.get("PROM_PARAM")
        endpoint = os.environ.get("PROM_ENDPOINT")
        if parameter:
            import boto3

            ssm = boto3.client("ssm")
            value = ssm.get_parameter(Name=parameter, WithDecryption=True)
            _cache["sources"] = json.loads(value["Parameter"]["Value"])
        elif endpoint:
            _cache["sources"] = [{"query_url": endpoint, "user": "", "token": ""}]
        else:
            raise prometheus.PrometheusError("neither PROM_PARAM nor PROM_ENDPOINT is set")
    return _cache["sources"]


def publish(documents: dict[str, str]) -> None:
    bucket = os.environ.get("BUCKET_NAME")
    if not bucket:
        # The local dev stack has no S3; the invoke response carries the
        # verdict instead.
        return
    import boto3

    s3 = boto3.client("s3")
    for name, body in documents.items():
        s3.put_object(
            Bucket=bucket,
            Key=name,
            Body=body.encode(),
            ContentType=OBJECTS[name],
            CacheControl=CACHE_CONTROL,
        )


def frequency_groups(mani: dict) -> dict[int, list[str]]:
    """Checks grouped by how often they run. The window that turns samples
    into a verdict is a multiple of the probe interval, so checks on
    different intervals cannot share one query without the slower ones
    being judged on fewer samples than the faster."""
    groups: dict[int, list[str]] = {}
    for key, check in mani["checks"].items():
        groups.setdefault(check["frequency_minutes"], []).append(key)
    return groups


def latency_groups(mani: dict) -> dict[tuple[int, float], list[str]]:
    """Checks grouped by probe interval and latency budget. The interval
    sets the window and the budget sits inside the expression, so a group is
    the largest set one query can judge at once. A check declaring no budget
    states no opinion about latency and joins no group."""
    groups: dict[tuple[int, float], list[str]] = {}
    for key, check in mani["checks"].items():
        budget = check.get("latency_budget_ms")
        if budget is None:
            continue
        groups.setdefault((check["frequency_minutes"], budget), []).append(key)
    return groups


def query_metrics(mani: dict, now: datetime, today: date, since: datetime) -> tuple[dict, bool]:
    """Everything one run reads from Prometheus, merged across every source
    by job. Any failure anywhere yields the fully degraded render — never a
    500, never stale green presented as current, and never history written
    from a partial picture."""
    read: dict = {
        "success": {},
        "duration": {},
        "duration_range": {},
        "down_samples": {},
        "day_samples": {},
        "day_successes": {},
        "budget_samples": {},
    }
    page = mani["page"]
    elapsed = max(1, int((now - state.day_start(today, mani["site"]["timezone"])).total_seconds()))
    try:
        for source in prometheus_sources():
            for frequency, jobs in frequency_groups(mani).items():
                read["success"].update(
                    prometheus.instant(
                        source,
                        prometheus.up_query(
                            jobs, frequency, page["down_window_multiple"], page["down_quorum"]
                        ),
                        now,
                    )
                )
                read["down_samples"].update(
                    prometheus.paired_series(
                        source,
                        prometheus.success_counts_queries(jobs),
                        since,
                        now,
                        frequency * 60,
                    )
                )
                samples_query, successes_query = prometheus.day_totals_queries(jobs, elapsed)
                read["day_samples"].update(prometheus.instant(source, samples_query, now))
                read["day_successes"].update(prometheus.instant(source, successes_query, now))
            for (frequency, budget), jobs in latency_groups(mani).items():
                read["budget_samples"].update(
                    prometheus.paired_series(
                        source,
                        prometheus.budget_counts_queries(jobs, budget / 1000),
                        since,
                        now,
                        frequency * 60,
                    )
                )
            read["duration"].update(prometheus.instant(source, prometheus.INSTANT_DURATION, now))
            read["duration_range"].update(prometheus.latency_range(source, now))
        return read, False
    except prometheus.PrometheusError as error:
        _cache.pop("sources", None)
        print(f"degraded: {error}")
        return read, True


def record_history(tbl, mani: dict, previous: dict | None, read: dict, now, today) -> str | None:
    """Outages come from walking the series, so one survives the renderer
    having been down and carries a probe's timestamp rather than a render's.
    The day's rollup is recomputed from the source rather than incremented.

    Returns how far the series was read, which is the watermark the next run
    starts from. Skipped entirely on a degraded run, so a Grafana outage
    never corrupts history with false downtime and the gap is walked once
    Prometheus answers again."""
    page = mani["page"]
    expires_at = int((now + timedelta(days=page["retention_days"])).timestamp())
    previous_checks = (previous or {}).get("checks", {})
    watermark = None
    for key in mani["checks"]:
        cached = previous_checks.get(key, {})
        # Outages and degradations are the same walk over two fraction
        # series: one definition of a confirmed period, applied twice.
        for field, kind, before in (
            ("down_samples", store.OUTAGE, cached.get("up")),
            ("budget_samples", store.DEGRADED, cached.get("within_budget")),
        ):
            series = read[field].get(key, [])
            if series:
                watermark = series[-1][0] if watermark is None else max(watermark, series[-1][0])
            for transition in state.confirmed_transitions(
                series, page["down_window_multiple"], page["down_quorum"], before
            ):
                if transition["kind"] == "opened":
                    store.open_period(tbl, kind, key, transition["at"], expires_at)
                else:
                    store.close_period(tbl, kind, key, transition["at"])
    day = today.isoformat()
    for key, samples in read["day_samples"].items():
        store.put_rollup(
            tbl, key, day, int(samples), int(read["day_successes"].get(key, 0)), expires_at
        )
    return state.iso(state.moment(watermark)) if watermark else None


def read_history(tbl, mani: dict, today: date) -> tuple[dict, dict, dict]:
    page = mani["page"]
    first_day = (today - timedelta(days=page["history_days"] - 1)).isoformat()
    last_day = today.isoformat()
    rollups = {}
    outage_records = {}
    degraded_records = {}
    for key in mani["checks"]:
        rollups[key] = store.rollups(tbl, key, first_day, last_day)
        outage_records[key] = store.periods(tbl, store.OUTAGE, key)
        degraded_records[key] = store.periods(tbl, store.DEGRADED, key)
    return rollups, outage_records, degraded_records


def report_observations(mani: dict, success: dict | None, now: datetime, degraded: bool) -> None:
    """Tell Grafana that this run happened, and which checks it heard from.

    Never fatal: a report that cannot be sent must not be what stops the
    page from rendering."""
    observed = None if degraded else {key: key in success for key in mani["checks"]}
    rendered_at = int(now.timestamp())
    try:
        sources = prometheus_sources()
    except prometheus.PrometheusError as error:
        print(f"report: {error}")
        return
    for failure in report.publish(sources, report.payload(rendered_at, observed)):
        print(f"report: {failure}")


# Prometheus keeps a fortnight on the plan this runs on, so a gap longer
# than that is not walkable however long the renderer was away.
SERIES_HORIZON_DAYS = 13


def series_start(mani: dict, previous: dict | None, now: datetime) -> datetime:
    """Where to resume reading.

    Behind the watermark by a whole verdict window, not at it: a verdict
    needs several samples, and one run only ever adds one. Re-reading is
    free — an outage is keyed by the moment it started, so recording the
    same one twice writes the same record.

    A run that never completed left the watermark where it was, so the gap
    is walked whole rather than lost.
    """
    slowest = max(frequency_groups(mani), default=1)
    pad = timedelta(minutes=slowest * (mani["page"]["down_window_multiple"] + 1))
    horizon = now - timedelta(days=SERIES_HORIZON_DAYS)
    mark = (previous or {}).get("processed_through")
    if not mark:
        return horizon
    resume = state.parse_iso(mark) - pad
    return max(resume, horizon)


def render_handler(event, context):
    mani = manifest()
    # Resolved before anything else runs: an unknown zone is a configuration
    # error, and one that renders a plausible-looking page in the wrong
    # hours is worse than one that stops.
    now = datetime.now(UTC)
    today = state.site_today(now, mani["site"]["timezone"])
    tbl = store.table(os.environ["TABLE_NAME"], os.environ.get("DDB_ENDPOINT"))

    previous = store.get_latest(tbl)
    since = series_start(mani, previous, now)
    read, degraded = query_metrics(mani, now, today, since)
    processed_through = None
    if not degraded:
        processed_through = record_history(tbl, mani, previous, read, now, today)
    rollups, outage_records, degraded_records = read_history(tbl, mani, today)
    success, duration = read["success"], read["duration"]

    page_state = state.assemble(
        mani,
        now=now,
        success=success,
        duration=duration,
        budget_samples=read["budget_samples"],
        duration_range=read["duration_range"],
        rollups=rollups,
        outages=outage_records,
        degradations=degraded_records,
        previous=previous,
        today=today,
        version=os.environ.get("PAGE_VERSION"),
        repository=os.environ.get("PAGE_SOURCE"),
        degraded=degraded,
    )

    documents = {
        "index.html": render.render_page(page_state),
        "status.json": render.render_status(page_state),
        "badge.svg": badge.render_badge(page_state),
    }

    if not degraded:
        # A degraded run must not touch the snapshot: it still holds the
        # last real observation, and its rendered_at is what makes the
        # "showing state from ..." notice honest.
        store.put_latest(tbl, state.snapshot(page_state), processed_through)

    publish(documents)
    report_observations(mani, success, now, degraded)

    return {
        "statusCode": 200,
        "overall": page_state["overall"],
        "degraded": degraded,
        "bytes": {name: len(body) for name, body in documents.items()},
        "body": documents["index.html"],
    }
