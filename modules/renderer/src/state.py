"""Pure assembly of the render state: manifest + metric dicts + stored
history in, one state dict out. No I/O — this is what makes the page
unit-testable and preview.py possible without credentials.
"""

from datetime import date, datetime, timedelta

DEFAULT_PORTS = {"https": 443, "http": 80, "smtp": 25}


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
    return "operational"


def subtitle(check: dict) -> str:
    """host, port, and path are separate facts in the manifest, so the row
    subtitle is assembled, never parsed back out of a URL."""
    kind, host = check["type"], check["host"]
    if kind in ("https", "http"):
        port = "" if check["port"] == DEFAULT_PORTS[kind] else f":{check['port']}"
        path = check["path"] if check["path"] not in (None, "/") else ""
        return f"{host}{port}{path}"
    if kind == "smtp":
        return f"{host}:{check['port']}"
    return host


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


def detect_transitions(
    previous_checks: dict, current_up: dict[str, bool | None], now: datetime
) -> list[dict]:
    """up→down opens an outage, down→up closes one. Unknown on either side is
    no transition: absence of data is never treated as downtime."""
    transitions = []
    for key, up in current_up.items():
        if up is None:
            continue
        before = previous_checks.get(key)
        if before is None or before.get("up") is None or before["up"] == up:
            continue
        transitions.append({"key": key, "kind": "closed" if up else "opened", "at": iso(now)})
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
    version: str | None = None,
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
    today = now.date()

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
