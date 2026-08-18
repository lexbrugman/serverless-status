"""Pure assembly of the render state: manifest + metric dicts + stored
history in, one state dict out. No I/O — this is what makes the page
unit-testable and preview.py possible without credentials.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_PORTS = {"https": 443, "http": 80, "smtp": 25}


def site_today(now: datetime, timezone: str) -> date:
    """The calendar day the page is showing, in the site's own timezone.

    An instant is a moment and stays UTC; a day is a bucket, and a bucket
    needs a frame of reference. The page states one — the same one its
    clock and its outage log are rendered in — so the bars split where the
    reader's midnight is, not where UTC's happens to be.
    """
    return now.replace(tzinfo=now.tzinfo or UTC).astimezone(ZoneInfo(timezone)).date()


def check_state(up: bool | None, latency_ms: float | None, budget_ms: float | None) -> str:
    if up is None:
        return "unknown"
    if not up:
        return "down"
    if budget_ms is not None and latency_ms is not None and latency_ms > budget_ms:
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
    """One entry per calendar day ending today, oldest first; ratio None for
    days without samples."""
    by_date = {row["date"]: row for row in rollup_rows}
    days = []
    for offset in range(history_days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        row = by_date.get(day)
        ratio = None
        if row and row["samples"]:
            ratio = row["successes"] / row["samples"]
        days.append({"date": day, "ratio": ratio})
    return days


def window_ratio(days: list[dict], rollup_rows: list[dict]) -> float | None:
    """Sample-weighted success ratio over the days shown in the bar."""
    shown = {d["date"] for d in days}
    samples = successes = 0
    for row in rollup_rows:
        if row["date"] in shown:
            samples += row["samples"]
            successes += row["successes"]
    if not samples:
        return None
    return successes / samples


def day_start(today: date, timezone: str) -> datetime:
    """Midnight of the site's own day, as an instant. The rollup counts the
    day a reader recognises, not the one UTC happens to be having."""
    return datetime.combine(today, time.min, tzinfo=ZoneInfo(timezone))


def moment(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def confirmed_transitions(
    series: list[tuple[float, float]],
    window_multiple: int,
    quorum: float,
    before: bool | None,
) -> list[dict]:
    """Edges in a raw success series, as the shared definition of down sees
    them.

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
    window: list[float] = []
    run_start = None
    run_up = None
    for at, fraction in series:
        point_up = fraction >= quorum
        if point_up != run_up:
            run_up, run_start = point_up, at
        window.append(fraction)
        if len(window) > window_multiple:
            window.pop(0)
        if len(window) < min_samples:
            continue
        verdict = sum(window) / len(window) >= quorum
        if current is None:
            current = verdict
            continue
        if verdict != current:
            transitions.append(
                {"kind": "closed" if verdict else "opened", "at": iso(moment(run_start))}
            )
            current = verdict
    return transitions


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def assemble(
    manifest: dict,
    *,
    now: datetime,
    success: dict[str, float] | None = None,
    duration: dict[str, float] | None = None,
    duration_range: dict[str, list] | None = None,
    rollups: dict[str, list] | None = None,
    outages: dict[str, list] | None = None,
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
    previous_checks = (previous or {}).get("checks", {})
    if today is None:
        today = site_today(now, site["timezone"])

    checks = []
    for key, check in manifest["checks"].items():
        cached = previous_checks.get(key, {})
        if degraded:
            up = cached.get("up")
            latency_ms = cached.get("latency_ms")
        else:
            up = None if success is None or key not in success else success[key] >= 1
            latency_ms = None
            if duration and key in duration:
                latency_ms = round(duration[key] * 1000)

        state = check_state(up, latency_ms, check.get("latency_budget_ms"))

        since = None
        if up is not None:
            unchanged = cached.get("up") == up and cached.get("since")
            since = cached["since"] if unchanged else iso(now)

        spark = None
        if not degraded and duration_range and key in duration_range:
            spark = [None if value is None else value * 1000 for _, value in duration_range[key]]

        days = day_series(rollups.get(key, []), page["history_days"], today)
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
                "since": since,
                "days": days,
                "uptime_ratio": window_ratio(days, rollups.get(key, [])),
                "spark": spark,
            }
        )

    display_by_key = {c["key"]: c["display"] for c in checks}
    horizon = now - timedelta(days=page["outage_log_days"])
    incident_log = []
    for key, records in outages.items():
        for record in records:
            reference = record.get("ended_at") or iso(now)
            if reference < iso(horizon):
                continue
            incident_log.append(
                {
                    "key": key,
                    "display": display_by_key.get(key, key),
                    "started_at": record["started_at"],
                    "ended_at": record.get("ended_at"),
                    "duration_seconds": record.get("duration_seconds"),
                }
            )
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
        "outages": incident_log,
    }


def snapshot(state: dict) -> dict:
    """The SITE/LATEST payload: the previous-state input of the next run."""
    return {
        "rendered_at": state["generated_at"],
        "checks": {
            c["key"]: {
                "up": c["up"],
                "latency_ms": c["latency_ms"],
                "since": c["since"],
            }
            for c in state["checks"]
        },
    }
