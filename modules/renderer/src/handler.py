"""The Lambda entry point — orchestration only, no decisions.

Every decision lives in state/render/badge/theme (pure) or store/prometheus
(one I/O concern each); this file just wires the flow: query, detect, fold,
read, assemble, render, publish.
"""

import json
import os
from datetime import UTC, datetime, timedelta
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


def query_metrics(now: datetime) -> tuple[dict | None, dict | None, dict | None, bool]:
    """(success, duration, duration_range, degraded), merged across every
    source by job. Any failure anywhere yields the fully degraded render —
    never a 500, never stale green presented as current, and never history
    written from a partial picture."""
    success: dict = {}
    duration: dict = {}
    duration_range: dict = {}
    try:
        for source in prometheus_sources():
            success.update(prometheus.instant(source, prometheus.INSTANT_SUCCESS, now))
            duration.update(prometheus.instant(source, prometheus.INSTANT_DURATION, now))
            duration_range.update(prometheus.latency_range(source, now))
        return success, duration, duration_range, False
    except prometheus.PrometheusError as error:
        _cache.pop("sources", None)
        print(f"degraded: {error}")
        return None, None, None, True


def record_history(tbl, mani: dict, previous: dict | None, success, duration, now) -> None:
    """Transitions become outage records; the sample folds into today's
    rollup. Skipped entirely on a degraded run, so a Grafana outage never
    corrupts history with false downtime."""
    page = mani["page"]
    expires_at = int((now + timedelta(days=page["retention_days"])).replace(tzinfo=UTC).timestamp())
    current_up = {
        key: (None if key not in success else success[key] >= 1) for key in mani["checks"]
    }
    previous_checks = (previous or {}).get("checks", {})
    for transition in state.detect_transitions(previous_checks, current_up, now):
        if transition["kind"] == "opened":
            store.open_outage(tbl, transition["key"], transition["at"], expires_at)
        else:
            store.close_outage(tbl, transition["key"], transition["at"])
    today = now.date().isoformat()
    for key, up in current_up.items():
        if up is None:
            continue
        latency_ms = round(duration[key] * 1000) if key in duration else None
        store.update_rollup(tbl, key, today, up, latency_ms, expires_at)


def read_history(tbl, mani: dict, now: datetime) -> tuple[dict, dict]:
    page = mani["page"]
    first_day = (now.date() - timedelta(days=page["history_days"] - 1)).isoformat()
    today = now.date().isoformat()
    rollups = {}
    outage_records = {}
    for key in mani["checks"]:
        rollups[key] = store.rollups(tbl, key, first_day, today)
        outage_records[key] = store.outages(tbl, key)
    return rollups, outage_records


def report_observations(mani: dict, success: dict | None, now: datetime, degraded: bool) -> None:
    """Tell Grafana that this run happened, and which checks it heard from.

    Never fatal: a report that cannot be sent must not be what stops the
    page from rendering."""
    observed = None if degraded else {key: key in success for key in mani["checks"]}
    rendered_at = int(now.replace(tzinfo=UTC).timestamp())
    try:
        sources = prometheus_sources()
    except prometheus.PrometheusError as error:
        print(f"report: {error}")
        return
    for failure in report.publish(sources, report.payload(rendered_at, observed)):
        print(f"report: {failure}")


def render_handler(event, context):
    now = datetime.now(UTC).replace(tzinfo=None)
    mani = manifest()
    tbl = store.table(os.environ["TABLE_NAME"], os.environ.get("DDB_ENDPOINT"))

    previous = store.get_latest(tbl)
    success, duration, duration_range, degraded = query_metrics(now)
    if not degraded:
        record_history(tbl, mani, previous, success, duration, now)
    rollups, outage_records = read_history(tbl, mani, now)

    page_state = state.assemble(
        mani,
        now=now,
        success=success,
        duration=duration,
        duration_range=duration_range,
        rollups=rollups,
        outages=outage_records,
        previous=previous,
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
        store.put_latest(tbl, state.snapshot(page_state), page_state["source"], degraded)

    publish(documents)
    report_observations(mani, success, now, degraded)

    return {
        "statusCode": 200,
        "overall": page_state["overall"],
        "degraded": degraded,
        "bytes": {name: len(body) for name, body in documents.items()},
        "body": documents["index.html"],
    }
