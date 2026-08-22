"""Pure assembly of the render state: manifest + metric dicts + stored
history in, one state dict out. No I/O — this is what makes the page
unit-testable and preview.py possible without credentials.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_PORTS = {"https": 443, "http": 80, "smtp": 25}

# Availability windows offered beside the bar's own, in days. One of them
# is the last 24 hours: a reader arrives asking whether the thing is flaky
# now, and a ninety-day figure cannot answer that question.
SHORT_WINDOW_DAYS = (1, 7, 30)

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc(moment: datetime) -> datetime:
    """Naive datetimes are UTC by convention throughout the renderer."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def site_today(now: datetime, timezone: str) -> date:
    """The calendar day the page is showing, in the site's own timezone.

    An instant is a moment and stays UTC; a day is a bucket, and a bucket
    needs a frame of reference. The page states one — the same one its
    clock and its outage log are rendered in — so the bars split where the
    reader's midnight is, not where UTC's happens to be.
    """
    return utc(now).astimezone(ZoneInfo(timezone)).date()


def check_state(up: bool | None, within_budget: bool | None) -> str:
    """The pill's verdict.

    Slow is judged the way down is — a quorum of probe locations over a
    window of instants — so neither state can be entered by a dissenting
    minority of locations or by a single sample. The page's overall banner
    is derived from these, so an unfiltered amber carries the whole page.
    """
    if up is None:
        return "unknown"
    if not up:
        return "down"
    if within_budget is False:
        return "slow"
    return "up"


def group_order(checks: dict) -> list[str]:
    """Groups ordered by their lowest member order, then name — derived from
    the checks themselves, so manifests merged from several stacks need no
    shared group list."""
    lowest: dict[str, int] = {}
    for check in checks.values():
        order = check.get("order", 50)
        if check["group"] not in lowest or order < lowest[check["group"]]:
            lowest[check["group"]] = order
    return [group for group, _ in sorted(lowest.items(), key=lambda item: (item[1], item[0]))]


def overall_state(states: list[str]) -> str:
    known = [s for s in states if s != "unknown"]
    if not known:
        return "unknown"
    downs = sum(1 for s in known if s == "down")
    if downs == len(known):
        return "major_outage"
    if downs:
        return "partial_outage"
    if any(s == "slow" for s in known):
        return "degraded"
    # A check nobody is hearing from is not a healthy check; it is one the
    # page has stopped being able to speak for. Ranked below every real
    # fault, because a failure that is visible outranks one that is not.
    if len(known) != len(states):
        return "partial_unknown"
    return "operational"


def address(check: dict) -> str:
    """host, port, and path are separate facts in the manifest, so an
    address is assembled, never parsed back out of a URL. Only departures
    from the protocol's defaults are worth the reader's attention: a port
    that is the standard one, or a path that is the root, says nothing the
    protocol tag has not said already."""
    kind, host = check["type"], check["host"]
    if kind == "ping":
        return host
    port = "" if check["port"] == DEFAULT_PORTS[kind] else f":{check['port']}"
    path = ""
    if kind in ("https", "http"):
        path = check["path"] if check["path"] not in (None, "/") else ""
    return f"{host}{port}{path}"


def subtitle(check: dict) -> str:
    """What the address says beyond the display name. The protocol is a
    tag of its own, and a name that already is the host leaves nothing to
    repeat — two checks on one host differ by their tag, not by a line of
    identical text."""
    full = address(check)
    display = check["display"]
    if full == display:
        return ""
    if full.startswith(display):
        return full[len(display) :]
    return full


def day_series(rollup_rows: list[dict], history_days: int, today: date) -> list[dict]:
    """One entry per calendar day ending today, oldest first.

    `probe_ratio` is None for a day with no samples, which is the same fact
    as the day being unobserved: the page can only speak for time it heard
    something in.
    """
    by_date = {row["date"]: row for row in rollup_rows}
    days = []
    for offset in range(history_days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        row = by_date.get(day)
        probe_ratio = None
        if row and row["samples"]:
            probe_ratio = row["successes"] / row["samples"]
        days.append({"date": day, "probe_ratio": probe_ratio})
    return days


def window_totals(days: list[dict], rollup_rows: list[dict]) -> dict:
    """Probe executions, successes, and the number of days that were
    observed at all, over the days the bar shows.

    The day count is what keeps the ratio honest. A window the page holds
    five days of is not a ninety-day record, and a bare percentage has no
    way of saying so.
    """
    shown = {d["date"] for d in days}
    samples = successes = 0
    for row in rollup_rows:
        if row["date"] in shown:
            samples += row["samples"]
            successes += row["successes"]
    observed = sum(1 for day in days if day["probe_ratio"] is not None)
    return {"samples": samples, "successes": successes, "observed_days": observed}


def window_ratio(days: list[dict], rollup_rows: list[dict]) -> float | None:
    """Sample-weighted probe-success ratio over the days shown in the bar.

    This is not availability and is never labelled as it. It counts probe
    executions, so one location failing while the service answers everyone
    else counts against it, and a check nobody heard from costs it nothing
    at all. It is the diagnostic beside the number, not the number.
    """
    totals = window_totals(days, rollup_rows)
    if not totals["samples"]:
        return None
    return totals["successes"] / totals["samples"]


def day_start(today: date, timezone: str) -> datetime:
    """Midnight of the site's own day, as an instant. The rollup counts the
    day a reader recognises, not the one UTC happens to be having."""
    return datetime.combine(today, time.min, tzinfo=ZoneInfo(timezone))


def moment(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def observed_intervals(
    days: list[dict], timezone: str, now: datetime
) -> list[tuple[datetime, datetime]]:
    """One interval per observed day, the last of them clipped to now.

    A day with no samples is a hole, not a quiet day. Time the page never
    heard from is left out of both sides of every ratio rather than counted
    as healthy — which is the failure a status page exists to be honest
    about, and the one a success ratio silently rewards.
    """
    now = utc(now)
    intervals = []
    for day in days:
        if day["probe_ratio"] is None:
            continue
        start = day_start(date.fromisoformat(day["date"]), timezone)
        intervals.append((start, min(start + timedelta(days=1), now)))
    return intervals


def _overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> float:
    """Seconds two intervals share; zero when they do not meet."""
    return max(0.0, (min(end_a, end_b) - max(start_a, start_b)).total_seconds())


def share_outside(
    intervals: list[tuple[datetime, datetime]],
    records: list[dict],
    start: datetime,
    end: datetime,
    now: datetime,
) -> float | None:
    """The share of observed time in [start, end) that no record covers.

    Availability against the outage records, performance against the
    degraded ones — one measurement, because both kinds of record are
    written by the same quorum over the same window. Wall-clock against a
    confirmed log means the bar, the figures beside it, the incident list
    and the message that woke somebody up all describe the same events.
    """
    span = sum(_overlap(s, e, start, end) for s, e in intervals)
    if not span:
        return None
    down = 0.0
    for record in records:
        began = parse_iso(record["started_at"])
        # An outage still open has not been down past the present.
        ended = utc(now) if record["ended_at"] is None else parse_iso(record["ended_at"])
        for s, e in intervals:
            down += _overlap(began, ended, max(s, start), min(e, end))
    # Every overlap is clipped inside the same intervals the span is summed
    # over, so downtime cannot exceed it — but float summation can overshoot
    # by an ulp, and a page reading -0.00% available is worse than one that
    # refuses to.
    return max(0.0, 1.0 - down / span)


def share_windows(
    intervals: list[tuple[datetime, datetime]],
    records: list[dict],
    now: datetime,
    history_days: int,
) -> list[dict]:
    """The bar's own window plus the shorter ones a reader actually asks
    about. A short window that is not shorter than the bar's is the bar's,
    and the same number printed twice is not a second data point."""
    now = utc(now)
    spans = [days for days in SHORT_WINDOW_DAYS if days < history_days] + [history_days]
    return [
        {
            "days": span,
            "ratio": share_outside(intervals, records, now - timedelta(days=span), now, now),
        }
        for span in spans
    ]


def current_verdict(
    series: list[tuple[float, float, float]], window_multiple: int, quorum: float
) -> bool | None:
    """The verdict the tail of a sample series supports, or None where there
    is too little of it to judge.

    The window, quorum and pooling confirmed_transitions uses, so what the
    pill says now and what the history records about the same samples cannot
    come apart.
    """
    min_samples = max(1, window_multiple - 1)
    window = series[-window_multiple:]
    if len(window) < min_samples:
        return None
    return sum(met for _, met, _ in window) / sum(of for _, _, of in window) >= quorum


def with_shares(
    days: list[dict],
    outages: list[dict],
    degraded: list[dict] | None,
    timezone: str,
    now: datetime,
) -> list[dict]:
    """Each day's own availability and performance, so every step of the bar
    is coloured by the definition of the figure standing next to it.

    Non-None for exactly the observed days: an observed day has already
    started, so its interval always has width. `degraded` is None for a
    check with no latency budget — no threshold is no opinion, which is not
    the same fact as never having crossed one.
    """
    now = utc(now)
    enriched = []
    for day in days:
        start = day_start(date.fromisoformat(day["date"]), timezone)
        end = start + timedelta(days=1)
        intervals = observed_intervals([day], timezone, now)
        enriched.append(
            {
                **day,
                "availability": share_outside(intervals, outages, start, end, now),
                "performance": (
                    None
                    if degraded is None
                    else share_outside(intervals, degraded, start, end, now)
                ),
            }
        )
    return enriched


def confirmed_transitions(
    series: list[tuple[float, float, float]],
    window_multiple: int,
    quorum: float,
    before: bool | None,
) -> list[dict]:
    """Edges in a series of (at, met, of) samples, as the shared definition
    sees them.

    The window pools both sides — successes over executions, not the mean of
    per-instant fractions — because that is what up_query asks Prometheus
    and what the alert rule fires on. Two forms that agree while every
    instant has the same number of locations reporting are still two forms,
    and the page and the pager may not answer to different ones.

    Reading the series rather than comparing one run against the last is
    what makes an incident survive the renderer being down, and what lets
    it carry a probe's timestamp instead of a render's.

    A verdict needs a window of samples; the outage started when the
    service did. So a confirmed change is stamped at the first sample of
    the run that confirmed it, never at the moment the window filled — the
    difference is the whole debounce, and it would land in every duration.

    Unknown on either side is no transition: absence of data is never
    treated as downtime.
    """
    min_samples = max(1, window_multiple - 1)
    transitions = []
    current = before
    window: list[tuple[float, float]] = []
    run_start = None
    run_ok = None
    for at, met, of in series:
        point_ok = met / of >= quorum
        if point_ok != run_ok:
            run_ok, run_start = point_ok, at
        window.append((met, of))
        if len(window) > window_multiple:
            window.pop(0)
        if len(window) < min_samples:
            continue
        verdict = sum(m for m, _ in window) / sum(o for _, o in window) >= quorum
        if current is None:
            current = verdict
            continue
        if verdict != current:
            transitions.append(
                {"kind": "closed" if verdict else "opened", "at": iso(moment(run_start))}
            )
            current = verdict
    return transitions


def in_window(record: dict, horizon: datetime, now: datetime) -> bool:
    """Whether a confirmed period belongs in a log reaching back to horizon.

    Judged on when it ended, so an outage leaves a log only once it is both
    over and old, and one still open is in every window that reaches the
    present — a reader must never have to widen a window to find the
    incident that is happening to them right now.

    One predicate for both logs. The row's reaches as far back as its own
    bar so every coloured step has an entry explaining it; the page's
    reaches outage_log_days. Two windows, but not two definitions of what
    falls inside one.
    """
    return (record.get("ended_at") or iso(now)) >= iso(horizon)


def incidents_within(
    sources: list[tuple[str, list[dict]]], horizon: datetime, now: datetime
) -> list[dict]:
    """Both kinds of confirmed period as one list, newest first.

    A confirmed degradation colours a day and moves a figure, so leaving it
    out would be the one place a reader could watch the page react to
    something it refuses to name.
    """
    entries = [
        {
            "kind": kind,
            "started_at": record["started_at"],
            "ended_at": record.get("ended_at"),
            "duration_seconds": record.get("duration_seconds"),
        }
        for kind, records in sources
        for record in records
        if in_window(record, horizon, now)
    ]
    entries.sort(key=lambda entry: entry["started_at"], reverse=True)
    return entries


def iso(moment: datetime) -> str:
    return moment.strftime(ISO_FORMAT)


def parse_iso(text: str) -> datetime:
    """The inverse of iso(). Stored timestamps are UTC and say so."""
    return datetime.strptime(text, ISO_FORMAT).replace(tzinfo=UTC)


def assemble(
    manifest: dict,
    *,
    now: datetime,
    success: dict[str, float] | None = None,
    duration: dict[str, float] | None = None,
    budget_samples: dict[str, list] | None = None,
    duration_range: dict[str, list] | None = None,
    rollups: dict[str, list] | None = None,
    outages: dict[str, list] | None = None,
    degradations: dict[str, list] | None = None,
    previous: dict | None = None,
    today: date | None = None,
    version: str | None = None,
    repository: str | None = None,
    degraded: bool = False,
) -> dict:
    """Build the state dict the renderers consume.

    Degraded is honest: with no fresh metrics the per-check state comes from
    the cached snapshot, the source says so, and the page will say so too.
    """
    site, page = manifest["site"], manifest["page"]
    rollups = rollups or {}
    outages = outages or {}
    degradations = degradations or {}
    previous_checks = (previous or {}).get("checks", {})
    if today is None:
        today = site_today(now, site["timezone"])

    checks = []
    for key, check in manifest["checks"].items():
        cached = previous_checks.get(key, {})
        if degraded:
            up = cached.get("up")
            latency_ms = cached.get("latency_ms")
            within_budget = cached.get("within_budget")
        else:
            up = None if success is None or key not in success else success[key] >= 1
            latency_ms = None
            if duration and key in duration:
                latency_ms = round(duration[key] * 1000)
            within_budget = current_verdict(
                (budget_samples or {}).get(key, []),
                page["down_window_multiple"],
                page["down_quorum"],
            )

        state = check_state(up, within_budget)

        since = None
        if up is not None:
            unchanged = cached.get("up") == up and cached.get("since")
            since = cached["since"] if unchanged else iso(now)

        spark = None
        if not degraded and duration_range and key in duration_range:
            spark = [None if value is None else value * 1000 for _, value in duration_range[key]]

        rollup_rows = rollups.get(key, [])
        records = outages.get(key, [])
        budget = check.get("latency_budget_ms")
        slow_records = None if budget is None else degradations.get(key, [])
        days = with_shares(
            day_series(rollup_rows, page["history_days"], today),
            records,
            slow_records,
            site["timezone"],
            now,
        )
        intervals = observed_intervals(days, site["timezone"], now)
        totals = window_totals(days, rollup_rows)
        # As far back as this row's own bar. A red step the list cannot
        # account for is a page that looks like it is holding something
        # back, and the records are already in hand either way.
        row_log = incidents_within(
            (("down", records), ("slow", slow_records or [])),
            now - timedelta(days=page["history_days"]),
            now,
        )
        checks.append(
            {
                "key": key,
                "display": check["display"],
                "group": check["group"],
                "type": check["type"],
                "subtitle": subtitle(check),
                "state": state,
                "up": up,
                "latency_ms": latency_ms,
                "latency_budget_ms": budget,
                "within_budget": within_budget,
                "since": since,
                "days": days,
                "availability": share_windows(intervals, records, now, page["history_days"]),
                "performance": (
                    None
                    if budget is None
                    else share_windows(intervals, slow_records, now, page["history_days"])
                ),
                "probe_success_ratio": window_ratio(days, rollup_rows),
                "incidents": row_log,
                "observed_days": totals["observed_days"],
                "spark": spark,
            }
        )

    display_by_key = {c["key"]: c["display"] for c in checks}
    # One flat log, reaching as far as the record does. Narrowing is the
    # reader's view of it: the page's section shows outage_log_days of it
    # because "recent" is the question that section answers, and a row
    # shows its own bar's worth. A consumer of status.json gets the whole
    # thing and can reproduce either — the alternative is a machine output
    # that holds less than the page it describes.
    horizon = now - timedelta(days=page["history_days"])
    incident_log = []
    for kind, source in (("down", outages), ("slow", degradations)):
        for key, records in source.items():
            # Keyed off the records, not off the checks, so a period
            # belonging to a check the manifest no longer declares still
            # surfaces rather than vanishing with the declaration.
            for entry in incidents_within(((kind, records),), horizon, now):
                incident_log.append({"key": key, "display": display_by_key.get(key, key), **entry})
    incident_log.sort(key=lambda o: o["started_at"], reverse=True)

    groups = [
        {
            "name": name,
            "checks": sorted(
                (c for c in checks if c["group"] == name),
                key=lambda c: (manifest["checks"][c["key"]].get("order", 50), c["key"]),
            ),
        }
        for name in group_order(manifest["checks"])
    ]

    return {
        "site": site,
        "page": page,
        "generated_at": iso(now),
        "source": "cache" if degraded else "grafana",
        "cached_at": (previous or {}).get("rendered_at"),
        "degraded": degraded,
        "overall": overall_state([c["state"] for c in checks]),
        "version": version,
        "repository": repository,
        "groups": groups,
        "checks": checks,
        "incidents": incident_log,
    }


def snapshot(state: dict) -> dict:
    """The SITE/LATEST payload: the previous-state input of the next run."""
    return {
        "rendered_at": state["generated_at"],
        "checks": {
            c["key"]: {
                "up": c["up"],
                "latency_ms": c["latency_ms"],
                "within_budget": c["within_budget"],
                "since": c["since"],
            }
            for c in state["checks"]
        },
    }
