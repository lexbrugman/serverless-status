"""The four fixture states: all-green, one-down, degraded-slow, stale-cache.

Each is a canned Prometheus response plus a DynamoDB-shaped seed (rollup rows
and outage records), generated deterministically *relative to the given now*
— dates in a committed file would go stale, and a status page fixture whose
"today" is months old renders a page that lies about staleness.
"""

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

STATES = ("all-green", "one-down", "degraded-slow", "stale-cache")

BASE_LATENCY_SECONDS = {
    "website": 0.142,
    "api": 0.310,
    "docs": 0.185,
    "mail-inbound": 0.460,
    "mail-inbound-backup": 0.520,
    "webmail": 0.225,
    "office-uplink": 0.012,
    "dns": 0.009,
    "vpn": 0.190,
}

# (check key, days ago, duration in probe intervals) — history every fixture
# shares. The docs outage predates the 30-day log window on purpose: it shows
# in the uptime bar but not in the incident list.
HISTORY_OUTAGES = [
    ("api", 8, 3),
    ("office-uplink", 20, 4),
    ("docs", 35, 2),
]

# (check key, days ago, duration in probe intervals). Only a check with a
# budget can have one, and only a confirmed one colours a day: a minority of
# probe locations past the budget never reaches this list.
HISTORY_DEGRADATIONS = [
    ("api", 12, 6),
    ("api", 41, 4),
]


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(moment: datetime) -> float:
    """Epoch seconds for a naive-UTC datetime (the convention throughout)."""
    return moment.replace(tzinfo=UTC).timestamp()


def manifest() -> dict:
    return json.loads((Path(__file__).parent / "manifest.json").read_text())


def _vector(values: dict[str, float], now: datetime) -> dict:
    ts = _ts(now)
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"job": job}, "value": [ts, str(value)]} for job, value in values.items()
            ],
        },
    }


def _matrix(series: dict[str, list[tuple[float, float]]]) -> dict:
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"job": job},
                    "values": [[ts, str(value)] for ts, value in points],
                }
                for job, points in series.items()
            ],
        },
    }


def _samples_per_day(check: dict) -> int:
    """Executions a day at the check's own interval — the manifest states it,
    so a fixture never has to know a type's default."""
    return 1440 // check["frequency_minutes"]


RANGE_POINTS = 97


def _range_series(mani: dict, now: datetime, slow_api: bool) -> dict:
    """The 24-hour grid a range query returns: both ends inclusive, so 97
    points at a 15-minute step, the last of them now."""
    series = {}
    for key in mani["checks"]:
        rng = random.Random(f"range:{key}")
        base = BASE_LATENCY_SECONDS[key]
        points = []
        for i in range(RANGE_POINTS):
            ts = _ts(now) - (RANGE_POINTS - 1 - i) * 900
            value = base * rng.uniform(0.85, 1.35)
            if slow_api and key == "api" and i > 89:
                value = 2.4 * rng.uniform(0.9, 1.1)
            points.append((ts, round(value, 4)))
        series[key] = points
    return series


# One probe location, matching the checks module's own default, so a
# denominator is always one and the numerator carries the verdict.
LOCATIONS = 1.0


def _success_counts(mani: dict, now: datetime, down: set[str]) -> tuple[dict, dict]:
    """Twelve per-instant (locations succeeding, locations reporting) pairs
    per check, ending now. A down check has been failing for the last four
    of them, which is long enough for the verdict window to have confirmed
    it."""
    met, of = {}, {}
    for key, check in mani["checks"].items():
        step = check["frequency_minutes"] * 60
        stamps = [_ts(now) - (11 - i) * step for i in range(12)]
        met[key] = [
            (at, 0.0 if key in down and i >= 8 else LOCATIONS) for i, at in enumerate(stamps)
        ]
        of[key] = [(at, LOCATIONS) for at in stamps]
    return met, of


def _budget_counts(mani: dict, now: datetime, slow: set[str]) -> tuple[dict, dict]:
    """The same pairs against the latency budget, for the checks that
    declare one. A slow check has been missing it for the last four
    instants, which is long enough for the verdict window to confirm."""
    met, of = {}, {}
    for key, check in mani["checks"].items():
        if check["latency_budget_ms"] is None:
            continue
        step = check["frequency_minutes"] * 60
        stamps = [_ts(now) - (11 - i) * step for i in range(12)]
        met[key] = [
            (at, 0.0 if key in slow and i >= 8 else LOCATIONS) for i, at in enumerate(stamps)
        ]
        of[key] = [(at, LOCATIONS) for at in stamps]
    return met, of


def _day_totals(mani: dict, now: datetime, down: set[str]) -> tuple[dict, dict]:
    """Executions and successes so far today, as Prometheus would count
    them — the rollup is recomputed from these rather than incremented."""
    elapsed = now.hour * 3600 + now.minute * 60
    samples, successes = {}, {}
    for key, check in mani["checks"].items():
        per_day = _samples_per_day(check)
        count = max(1, int(per_day * elapsed / 86400))
        samples[key] = float(count)
        successes[key] = float(max(0, count - (4 if key in down else 0)))
    return samples, successes


def _rollups(mani: dict, now: datetime, ongoing: dict[str, int]) -> dict:
    """~120 days of daily rows per check; the assembly trims to history_days."""
    failed_days = {(key, ago): failures for key, ago, failures in HISTORY_OUTAGES}
    rollups = {}
    for key, check in mani["checks"].items():
        rng = random.Random(f"rollup:{key}")
        per_day = _samples_per_day(check)
        rows = []
        for ago in range(120, -1, -1):
            day = now.date() - timedelta(days=ago)
            samples = per_day
            if ago == 0:
                elapsed = now.hour * 3600 + now.minute * 60
                samples = max(1, int(per_day * elapsed / 86400))
            failures = failed_days.get((key, ago), 0)
            # A sprinkle of single-probe blips, so the bar shows amber days.
            if not failures and rng.random() < 0.04:
                failures = 1
            failures = min(failures, samples)
            if ago == 0:
                failures += ongoing.get(key, 0)
                failures = min(failures, samples)
            rows.append(
                {
                    "date": day.isoformat(),
                    "samples": samples,
                    "successes": samples - failures,
                }
            )
        rollups[key] = rows
    return rollups


def _degraded_records(mani: dict, now: datetime, open_slow: dict[str, datetime]) -> dict:
    """Confirmed degradations, the amber counterpart of the outage records
    and written by the same walk over a fraction series."""
    return _periods(mani, now, HISTORY_DEGRADATIONS, open_slow, "degraded")


def _outage_records(mani: dict, now: datetime, open_outages: dict[str, datetime]) -> dict:
    return _periods(mani, now, HISTORY_OUTAGES, open_outages, "outage")


def _periods(
    mani: dict, now: datetime, history: list, open_now: dict[str, datetime], salt: str
) -> dict:
    records = {}
    for key, ago, failures in history:
        check = mani["checks"][key]
        duration = failures * check["frequency_minutes"] * 60
        offset = 9 if salt == "outage" else 14
        started = datetime.combine(now.date(), datetime.min.time()) - timedelta(
            days=ago, hours=-offset, minutes=-14
        )
        records.setdefault(key, []).append(
            {
                "started_at": _iso(started),
                "ended_at": _iso(started + timedelta(seconds=duration)),
                "duration_seconds": duration,
            }
        )
    for key, started in open_now.items():
        records.setdefault(key, []).append(
            {"started_at": _iso(started), "ended_at": None, "duration_seconds": None}
        )
    return records


def _previous(mani: dict, now: datetime, rendered_ago_seconds: int, down: set[str]) -> dict:
    """The snapshot a degraded run renders from, so it carries every field
    such a run has no fresh answer for — the latency verdict included."""
    rng = random.Random("previous")
    checks = {}
    for key in mani["checks"]:
        if key in down:
            checks[key] = {
                "up": False,
                "latency_ms": None,
                "since": _iso(now - timedelta(minutes=23)),
            }
        else:
            checks[key] = {
                "up": True,
                "latency_ms": round(BASE_LATENCY_SECONDS[key] * 1000 * rng.uniform(0.9, 1.2)),
                "within_budget": True,
                "since": _iso(now - timedelta(days=8, hours=3)),
            }
    return {"rendered_at": _iso(now - timedelta(seconds=rendered_ago_seconds)), "checks": checks}


def load(name: str, now: datetime) -> dict:
    """The raw inputs one fixture state feeds the handler-shaped assembly:
    manifest, canned Prometheus responses (None when unreachable), rollup
    rows, outage records, and the previous snapshot."""
    if name not in STATES:
        raise ValueError(f"unknown fixture state {name!r} (expected one of {STATES})")
    mani = manifest()

    down = {"mail-inbound"} if name == "one-down" else set()
    slow_api = name == "degraded-slow"

    success = {key: 0.0 if key in down else 1.0 for key in mani["checks"]}
    duration = {}
    for key in mani["checks"]:
        rng = random.Random(f"instant:{key}")
        duration[key] = round(BASE_LATENCY_SECONDS[key] * rng.uniform(0.9, 1.2), 4)
    if slow_api:
        duration["api"] = 2.41
    duration = {key: value for key, value in duration.items() if key not in down}

    open_outages = dict.fromkeys(down, now - timedelta(minutes=23))
    ongoing_failures = dict.fromkeys(down, 5)
    # The verdict is read off the fraction series, so a fixture that means
    # to render amber says so there rather than through a duration.
    slow = {"api"} if slow_api else set()
    open_degradations = dict.fromkeys(slow, now - timedelta(minutes=23))

    prometheus = None
    if name != "stale-cache":
        day_samples, day_successes = _day_totals(mani, now, down)
        success_met, success_of = _success_counts(mani, now, down)
        budget_met, budget_of = _budget_counts(mani, now, slow)
        prometheus = {
            "success": _vector(success, now),
            "duration": _vector(duration, now),
            "duration_range": _matrix(_range_series(mani, now, slow_api)),
            "success_met": _matrix(success_met),
            "success_of": _matrix(success_of),
            "day_samples": _vector(day_samples, now),
            "day_successes": _vector(day_successes, now),
            "budget_met": _matrix(budget_met),
            "budget_of": _matrix(budget_of),
        }

    return {
        "manifest": mani,
        "prometheus": prometheus,
        "rollups": _rollups(mani, now, ongoing_failures),
        "outages": _outage_records(mani, now, open_outages),
        "degradations": _degraded_records(mani, now, open_degradations),
        "previous": _previous(
            mani,
            now,
            rendered_ago_seconds=2820 if name == "stale-cache" else 60,
            down=down,
        ),
        "degraded": name == "stale-cache",
    }


def build_state(
    name: str, now: datetime, version: str | None = None, repository: str | None = None
) -> dict:
    """Fixture inputs through the real parse + assembly, exactly as the
    handler wires them. Callers must have modules/renderer/src on sys.path.
    """
    import prometheus as prom
    import state as state_module

    fixture = load(name, now)
    parsed = {
        "success": None,
        "duration": None,
        "duration_range": None,
        "budget_samples": None,
    }
    if fixture["prometheus"]:
        canned = fixture["prometheus"]
        parsed = {
            "success": prom.parse_vector(canned["success"]),
            "duration": prom.parse_vector(canned["duration"]),
            "duration_range": prom.parse_matrix(canned["duration_range"]),
            "budget_samples": prom.paired(
                prom.parse_matrix(canned["budget_met"]),
                prom.parse_matrix(canned["budget_of"]),
            ),
        }
    return state_module.assemble(
        fixture["manifest"],
        now=now,
        success=parsed["success"],
        duration=parsed["duration"],
        budget_samples=parsed["budget_samples"],
        duration_range=parsed["duration_range"],
        rollups=fixture["rollups"],
        outages=fixture["outages"],
        degradations=fixture["degradations"],
        previous=fixture["previous"],
        version=version,
        repository=repository,
        degraded=fixture["degraded"],
    )
