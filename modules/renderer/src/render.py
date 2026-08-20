"""Pure rendering: state dict in, HTML (or status.json) string out. No I/O.

Zero external dependencies at render time and at view time: inline CSS,
inline SVG, system font stack, no CDN, no font host, no analytics. A status
page that needs a third party to render is a status page that goes down with
the thing it reports on.
"""

import html
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import theme

STATUS_SCHEMA_VERSION = 2


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


# No fallback: the zone is resolved once, before anything renders, so by
# here it is known good. A silent drop to UTC would render every timestamp
# an hour or two wrong and look entirely correct doing it.
def _local_time(iso_utc: str, timezone: str) -> str:
    moment = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(timezone)).strftime("%d %b %Y, %H:%M %Z")


def _short_time(iso_utc: str, timezone: str) -> str:
    moment = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(timezone)).strftime("%d %b %H:%M")


def humanize_duration(seconds: float | None) -> str:
    if seconds is None:
        return "ongoing"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, hours, days = seconds // 60, seconds // 3600, seconds // 86400
    if minutes < 60:
        return f"{minutes} min"
    if hours < 24:
        rest = minutes % 60
        return f"{hours} h {rest} min" if rest else f"{hours} h"
    rest = hours % 24
    return f"{days} d {rest} h" if rest else f"{days} d"


def _percent(ratio: float | None) -> str:
    return f"{ratio:.2%}" if ratio is not None else "—"


def _window_label(days: int) -> str:
    """A single day is the window a reader counts in hours."""
    return "24h" if days == 1 else f"{days}d"


def _window_line(label: str, windows: list[dict]) -> str:
    text = " · ".join(
        [label] + [f"{_window_label(w['days'])}: {_percent(w['ratio'])}" for w in windows]
    )
    return f'<div class="windows"><span>{text}</span></div>'


def _detail(check: dict, history_days: int) -> str:
    """The shorter windows and the raw probe ratio, one interaction away.

    A status page answers "is it working" first, and the figures that
    answer "how do you know" are a different question — beside the answer
    they crowd it out, and a reader cannot tell which of nine percentages
    was the one to read. <details> discloses them with no script, which the
    zero-dependency rule requires and a phone needs.
    """
    lines = [_window_line("availability", check["availability"])]
    if check["latency_budget_ms"] is not None:
        lines.append(_window_line("within budget", check["performance"]))
    lines.append(
        '<div class="windows">'
        f"<span>probe success: {_percent(check['probe_success_ratio'])}</span>"
        f"<span>{check['observed_days']} of {history_days} days observed</span></div>"
    )
    return f'<details class="more"><summary>detail</summary>{"".join(lines)}</details>'


def _css(page: dict, accent: str) -> str:
    light = theme.css_variables("light")
    dark = theme.css_variables("dark")
    return f"""
:root{{{light}--accent:{accent};color-scheme:light dark}}
@media (prefers-color-scheme:dark){{:root{{{dark}}}}}
*{{box-sizing:border-box;margin:0}}
body{{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--surface);
  color:var(--ink);padding:24px 16px 48px}}
main{{max-width:840px;margin:0 auto}}
a{{color:var(--accent)}}
header{{display:flex;align-items:center;gap:12px;margin:16px 0 8px}}
header .logo svg{{display:block;height:36px;width:auto}}
h1{{font-size:22px;font-weight:650;letter-spacing:-.01em}}
.desc{{color:var(--ink-secondary);margin-bottom:20px}}
.banner{{display:flex;align-items:center;gap:14px;border-radius:12px;padding:18px 20px;
  margin:20px 0;color:#fff}}
.banner .dot{{width:14px;height:14px;border-radius:50%;background:#fff;opacity:.92;flex:none}}
.banner h2{{font-size:18px;font-weight:650}}
.banner time{{margin-left:auto;font-size:13px;opacity:.85;text-align:right}}
.b-operational{{background:var(--ok)}}.b-degraded{{background:var(--warn);color:#3b2a00}}
.b-partial_outage{{background:var(--serious);color:#3d1503}}.b-major_outage{{background:var(--critical)}}
.b-unknown,.b-partial_unknown{{background:var(--neutral);color:#1c1917}}
.notice{{border:1px solid var(--warn);border-radius:10px;padding:10px 14px;margin:16px 0;
  font-size:14px;background:color-mix(in srgb,var(--warn) 12%,transparent)}}
.group{{margin:28px 0}}
.group>h3{{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
  color:var(--ink-secondary);margin-bottom:10px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}}
.row{{padding:14px 18px}}
.row+.row{{border-top:1px solid var(--border)}}
.row-top{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}}
.name{{font-weight:600}}
.kind{{color:var(--ink-secondary);font-size:11px;font-weight:600;letter-spacing:.04em;
  text-transform:uppercase;border:1px solid var(--border);border-radius:6px;padding:1px 6px}}
.sub{{color:var(--ink-muted);font-size:13px}}
.row-now{{margin-left:auto;display:flex;align-items:center;gap:14px}}
.latency{{font-size:13px;color:var(--ink-secondary);font-variant-numeric:tabular-nums}}
.spark{{width:96px;height:24px;overflow:visible}}
.spark path{{stroke:var(--ink-muted);stroke-width:1.8;stroke-linejoin:round}}
.spark-base{{stroke:var(--border)}}
.spark-budget{{stroke:var(--warn);stroke-width:1;stroke-dasharray:2 2}}
.pill{{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 10px;
  font-size:13px;font-weight:600}}
.pill .glyph{{width:10px;height:10px;fill:currentColor}}
.p-up{{color:var(--ok-text);background:color-mix(in srgb,var(--ok) 13%,transparent)}}
.p-slow{{color:var(--warn-text);background:color-mix(in srgb,var(--warn) 16%,transparent)}}
.p-down{{color:var(--critical-text);background:color-mix(in srgb,var(--critical) 13%,transparent)}}
.p-unknown{{color:var(--ink-secondary);
  background:color-mix(in srgb,var(--neutral) 18%,transparent)}}
.row-bar{{display:flex;align-items:center;gap:12px;margin-top:10px}}
.bar{{flex:1;height:28px;display:block}}
.d-up{{fill:var(--ok)}}.d-slow{{fill:var(--warn)}}.d-down{{fill:var(--critical)}}
.d-unknown{{fill:var(--neutral);opacity:.45}}
.ratio{{font-size:13px;color:var(--ink-secondary);font-variant-numeric:tabular-nums;
  text-align:right;white-space:nowrap}}
.bar-caption{{display:flex;justify-content:space-between;color:var(--ink-muted);
  font-size:11px;margin-top:4px}}
.windows{{display:flex;justify-content:space-between;flex-wrap:wrap;gap:2px 16px;
  color:var(--ink-muted);font-size:11px;font-variant-numeric:tabular-nums;margin-top:2px}}
.more{{margin-top:2px}}
.more summary{{color:var(--ink-muted);font-size:11px;cursor:pointer;width:fit-content}}
.outages ul{{list-style:none;padding:0}}
.outages li{{display:flex;gap:10px;align-items:baseline;padding:10px 2px;flex-wrap:wrap;
  border-top:1px solid var(--border);font-size:14px}}
.outages li:first-child{{border-top:0}}
.outages .pill{{font-size:11px;padding:1px 8px}}
.outages .when{{color:var(--ink-secondary);font-variant-numeric:tabular-nums}}
.outages .dur{{margin-left:auto;color:var(--ink-secondary)}}
.dur.open{{color:var(--critical-text);font-weight:600}}
.empty{{color:var(--ink-muted);font-size:14px;padding:6px 2px}}
footer{{margin-top:36px;padding-top:16px;border-top:1px solid var(--border);
  color:var(--ink-muted);font-size:13px;display:flex;gap:8px;flex-wrap:wrap}}
footer .sep{{opacity:.6}}
@media (max-width:560px){{.spark{{display:none}}}}
"""


def _row(check: dict, page: dict) -> str:
    meta = theme.CHECK_STATES[check["state"]]
    spark = ""
    if check["spark"]:
        spark = theme.sparkline(check["spark"], budget_ms=check["latency_budget_ms"])
    latency = ""
    if check["latency_ms"] is not None:
        latency = f'<span class="latency">{check["latency_ms"]} ms</span>'
    history_days = page["history_days"]
    # The number beside the bar carries its own name: a bare percentage
    # there is read as availability whatever produced it, and the rest of
    # the figures answer a question the reader has not asked yet.
    full = {window["days"]: window["ratio"] for window in check["availability"]}
    headline = f"{_percent(full[history_days])} available"
    definition = f"share of observed time with no confirmed outage, over {history_days} days"

    # Worth stating only where it is not the whole window. A record the page
    # holds every day of needs no qualifier, and one that carries the note
    # anyway is a number saying nothing nine times out of ten.
    coverage = ""
    if check["observed_days"] < history_days:
        coverage = f"<span>{check['observed_days']} of {history_days} days observed</span>"

    # Only for a check that declared a budget: without one there is no
    # threshold to have met, and an empty line says nothing.
    compliance_line = ""
    if check["latency_budget_ms"] is not None:
        within = {window["days"]: window["ratio"] for window in check["performance"]}
        compliance_line = (
            f'<div class="windows"><span>{_percent(within[history_days])} within budget</span>'
            f"<span>budget {check['latency_budget_ms']:.0f} ms</span></div>"
        )
    # The tag is what tells two checks on one host apart; the subtitle is
    # empty whenever the address says no more than the name does.
    subtitle = ""
    if check["subtitle"]:
        subtitle = f'<span class="sub">{_esc(check["subtitle"])}</span>'
    return f"""<article class="row">
<div class="row-top">
  <span class="name">{_esc(check["display"])}</span>
  <span class="kind">{_esc(check["type"])}</span>
  {subtitle}
  <div class="row-now">{spark}{latency}
    <span class="pill p-{check["state"]}">{theme.state_glyph(check["state"])}{meta["label"]}</span>
  </div>
</div>
<div class="row-bar">{theme.uptime_bar(check["days"])}\
<span class="ratio" title="{_esc(definition)}">{headline}</span></div>
<div class="bar-caption"><span>{history_days} days ago</span>{coverage}<span>today</span></div>
{compliance_line}{_detail(check, history_days)}</article>"""


def _incident_item(incident: dict, timezone: str) -> str:
    started = _short_time(incident["started_at"], timezone)
    if incident["ended_at"]:
        duration = f'<span class="dur">{humanize_duration(incident["duration_seconds"])}</span>'
    else:
        duration = '<span class="dur open">ongoing</span>'
    # The pill the check itself wears, so a reader scanning the list sorts
    # outages from slowdowns by a colour they have already learned.
    kind = incident["kind"]
    return (
        f'<li><span class="name">{_esc(incident["display"])}</span>'
        f'<span class="pill p-{kind}">{theme.CHECK_STATES[kind]["label"]}</span>'
        f'<span class="when">{started}</span>{duration}</li>'
    )


def render_page(state: dict) -> str:
    site, page = state["site"], state["page"]
    timezone = site["timezone"]
    name = site["name"]
    title = site.get("title") or f"{name} status"
    overall = theme.OVERALL_STATES[state["overall"]]
    updated = _local_time(state["generated_at"], timezone)

    logo = f'<span class="logo">{site["logo_svg"]}</span>' if site.get("logo_svg") else ""
    description = (
        f'<p class="desc">{_esc(site["description"])}</p>' if site.get("description") else ""
    )

    degraded_notice = ""
    if state["degraded"]:
        cached = f" from {_local_time(state['cached_at'], timezone)}" if state["cached_at"] else ""
        degraded_notice = (
            '<div class="notice">Live monitoring data is currently unavailable — '
            f"showing the last known state{cached}.</div>"
        )

    groups = []
    for group in state["groups"]:
        rows = "".join(_row(check, page) for check in group["checks"])
        groups.append(
            f'<section class="group"><h3>{_esc(group["name"])}</h3>'
            f'<div class="card">{rows}</div></section>'
        )

    if state["incidents"]:
        items = "".join(_incident_item(i, timezone) for i in state["incidents"])
        incident_body = f"<ul>{items}</ul>"
    else:
        incident_body = (
            f'<p class="empty">No incidents in the last {page["outage_log_days"]} days.</p>'
        )

    links = [
        f'<a href="{_esc(link["url"])}">{_esc(link["label"])}</a>'
        for link in site.get("links") or []
    ]
    # What built this page, linked to the exact release when there is one.
    # Both facts come from the module pin, so a fork points at itself.
    version = ""
    if state.get("version"):
        label = f"serverless-status v{_esc(state['version'])}"
        repository = state.get("repository")
        if repository:
            url = f"https://github.com/{_esc(repository)}"
            if state["version"] != "local":
                url = f"{url}/releases/tag/{_esc(state['version'])}"
            version = f'<a href="{url}">{label}</a>'
        else:
            version = label
    footer_parts = [
        f"Last updated {updated}",
        *links,
        version,
        '<a href="status.json">status.json</a>',
        '<a href="badge.svg">badge.svg</a>',
    ]
    footer = '<span class="sep">·</span>'.join(
        f"<span>{part}</span>" for part in footer_parts if part
    )

    stale_after_ms = page["refresh_seconds"] * 3 * 1000
    script = (
        "(function(){var r=Date.parse(document.documentElement.dataset.renderedAt);"
        "function c(){document.getElementById('stale').hidden="
        f"(Date.now()-r)<{stale_after_ms};}}"
        "c();setInterval(c,30000);})();"
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-rendered-at="{state["generated_at"]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{page["refresh_seconds"]}">
<title>{_esc(title)}</title>
<link rel="icon" href="{theme.favicon_data_uri(state["overall"])}">
<style>{_css(page, site.get("accent") or "#16a34a")}</style>
</head>
<body>
<main>
<header>{logo}<h1>{_esc(name)}</h1></header>
{description}
<section class="banner b-{state["overall"]}" role="status">
  <span class="dot"></span><h2>{overall["label"]}</h2>
  <time datetime="{state["generated_at"]}">{updated}</time>
</section>
<div class="notice" id="stale" hidden>This page may be out of date — it was last
rendered {updated} and normally refreshes every {page["refresh_seconds"]} seconds.</div>
{degraded_notice}
{"".join(groups)}
<section class="outages group"><h3>Recent incidents</h3>{incident_body}</section>
<footer>{footer}</footer>
</main>
<script>{script}</script>
</body>
</html>
"""


def render_status(state: dict) -> str:
    """status.json — its own schema_version, independent of the manifest's:
    this one is a public contract with consumers."""
    checks = [
        {
            "key": c["key"],
            "display": c["display"],
            "group": c["group"],
            # Two checks may share a host and a display name; the protocol
            # is what tells them apart here as well as on the page.
            "type": c["type"],
            "state": c["state"],
            "latency_ms": c["latency_ms"],
            # Availability is time-weighted against the incident log; probe
            # success counts executions. Separate names because they answer
            # different questions and routinely disagree.
            "availability": c["availability"],
            "probe_success_ratio": c["probe_success_ratio"],
            # Compliance is only meaningful against a declared budget, and
            # the budget travels with it so a consumer need not guess.
            "latency_budget_ms": c["latency_budget_ms"],
            "performance": c["performance"],
            "observed_days": c["observed_days"],
            "window_days": state["page"]["history_days"],
            "last_change": c["since"],
        }
        for c in state["checks"]
    ]
    incidents = [
        {
            "key": i["key"],
            "kind": i["kind"],
            "started_at": i["started_at"],
            "ended_at": i["ended_at"],
            "duration_seconds": i["duration_seconds"],
        }
        for i in state["incidents"]
    ]
    return json.dumps(
        {
            "schema_version": STATUS_SCHEMA_VERSION,
            "generated_at": state["generated_at"],
            "degraded": state["degraded"],
            "overall": state["overall"],
            "checks": checks,
            "incidents": incidents,
        },
        indent=2,
    )
