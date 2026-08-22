"""Pure rendering: state dict in, HTML (or status.json) string out. No I/O.

Zero external dependencies at render time and at view time: inline CSS,
inline SVG, system font stack, no CDN, no font host, no analytics. A status
page that needs a third party to render is a status page that goes down with
the thing it reports on.
"""

import html
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import theme

# By name, not as a module: `state` is the parameter every renderer here
# takes. One definition of what falls inside a window, shared with the
# assembly that wrote the log.
from state import in_window, parse_iso

STATUS_SCHEMA_VERSION = 3


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


def _detail(check: dict) -> str:
    """The shorter windows, one interaction away.

    A status page answers "is it working" first, and the figures that
    answer "how do you know" are a different question — beside the answer
    they crowd it out, and a reader cannot tell which of nine percentages
    was the one to read. <details> discloses them with no script, which the
    zero-dependency rule requires and a phone needs; script only remembers
    which one was open, and its absence costs the reader the memory, never
    the figures.

    Every figure here is measured against the confirmed log, the same way
    the bar and the incident list are. The probe-success ratio used to
    stand among them and no longer does: it counts executions, so a
    minority of locations failing while the quorum reads up moved it
    without moving anything else on the page. Several locations are how
    the verdict is made, not something the reader is meant to audit — the
    ratio described the instrument, and a reader has no way to tell an
    instrument's noise floor from a service's. It stays in status.json,
    where a consumer that wants it can ask.

    How much of the window was observed is stated under the bar instead,
    where it costs no height of its own and sits against the greyed steps
    it is describing. Repeating it here said the same thing twice to the
    one reader who had opened the disclosure.

    data-key is what lets the open one be reopened after a refresh; the
    key is a Prometheus job label, so it is already [a-z0-9-] and stable
    across renders.
    """
    lines = [_window_line("availability", check["availability"])]
    if check["latency_budget_ms"] is not None:
        lines.append(_window_line("within budget", check["performance"]))
    return (
        f'<details class="more" data-key="{_esc(check["key"])}:detail">'
        f"<summary>detail</summary>{''.join(lines)}</details>"
    )


def _row_incidents(check: dict, timezone: str) -> str:
    """This row's own confirmed periods, disclosed the way its figures are.

    Reaching as far back as the bar above it, so the list accounts for
    every coloured step in it — a red day with nothing to explain it is
    the one thing a status page cannot afford to look like it is doing.

    Rendered only for a check that has any. The count belongs in the
    summary because the question a reader opens this with is how many, and
    a disclosure that answers it while still shut has saved them the
    click; a check with none has an all-green bar saying so already, and a
    row per check reading "incidents (0)" is nine lines of nothing.
    """
    if not check["incidents"]:
        return ""
    items = "".join(_incident_item(i, timezone, named=False) for i in check["incidents"])
    return (
        f'<details class="more" data-key="{_esc(check["key"])}:incidents">'
        f"<summary>incidents ({len(check['incidents'])})</summary>"
        f'<ul class="log">{items}</ul></details>'
    )


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
/* Shut, the summaries sit side by side and cost one line between them.
   Opened, the one in question claims a full row rather than reading in a
   column half the page wide. */
.more-row{{display:flex;flex-wrap:wrap;gap:2px 16px;align-items:flex-start}}
.more-row details[open]{{flex:1 1 100%}}
.log{{list-style:none;padding:0}}
.log li{{display:flex;gap:10px;align-items:baseline;padding:10px 2px;flex-wrap:wrap;
  border-top:1px solid var(--border);font-size:14px}}
.log li:first-child{{border-top:0}}
.log .pill{{font-size:11px;padding:1px 8px}}
.log .when{{color:var(--ink-secondary);font-variant-numeric:tabular-nums}}
.log .dur{{margin-left:auto;color:var(--ink-secondary)}}
.more-row .log li{{font-size:13px;padding:6px 2px}}
.dur.open{{color:var(--critical-text);font-weight:600}}
.empty{{color:var(--ink-muted);font-size:14px;padding:6px 2px}}
footer{{margin-top:36px;padding-top:16px;border-top:1px solid var(--border);
  color:var(--ink-muted);font-size:13px;display:flex;gap:8px;flex-wrap:wrap}}
footer .sep{{opacity:.6}}
@media (max-width:560px){{.spark{{display:none}}}}
"""


def _script(stale_after_ms: int) -> str:
    """Two enhancements, both of which the page is complete without.

    The staleness notice: a meta-refresh that cannot reach the network
    leaves the last render on screen indefinitely, and a page that has
    stopped updating must say so rather than keep presenting old figures
    as current.

    The open disclosures: that same refresh reloads the document every
    minute, and a browser restores scroll across it but not the open state
    of a <details>. A reader who opened one to read the windows had it shut
    under them within the minute, which made the disclosure unusable for
    exactly the reader who wanted it. The open keys are recorded on toggle
    and reapplied on load — sessionStorage, not local, so it is the tab's
    choice and not a preference the page has decided to keep. The script
    is the last thing in the body and runs synchronously, so the browser
    has the finished document before it paints.

    Storage throws rather than returns null when a browser has disabled it,
    and a page that fails to render because it could not remember which
    disclosure was open would be trading the whole page for a nicety.
    """
    return (
        "(function(){var r=Date.parse(document.documentElement.dataset.renderedAt);"
        "function c(){document.getElementById('stale').hidden="
        f"(Date.now()-r)<{stale_after_ms};}}"
        "c();setInterval(c,30000);"
        "var d=document.querySelectorAll('details[data-key]'),k='detail-open',o=[];"
        "try{o=JSON.parse(sessionStorage.getItem(k));}catch(e){}"
        "if(!Array.isArray(o))o=[];"
        "function s(){var n=[];Array.prototype.forEach.call(d,function(x){"
        "if(x.open)n.push(x.dataset.key);});"
        "try{sessionStorage.setItem(k,JSON.stringify(n));}catch(e){}}"
        "Array.prototype.forEach.call(d,function(x){"
        "if(o.indexOf(x.dataset.key)>=0)x.open=true;"
        "x.addEventListener('toggle',s);});"
        "})();"
    )


def _row(check: dict, page: dict, timezone: str) -> str:
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
{compliance_line}<div class="more-row">{_detail(check)}\
{_row_incidents(check, timezone)}</div></article>"""


def _incident_item(incident: dict, timezone: str, *, named: bool) -> str:
    """One entry, for either log. Named in the page's, where the whole
    point is which check it was; unnamed in a row's, where the row has
    said so already and repeating it nine times is furniture."""
    started = _short_time(incident["started_at"], timezone)
    if incident["ended_at"]:
        duration = f'<span class="dur">{humanize_duration(incident["duration_seconds"])}</span>'
    else:
        duration = '<span class="dur open">ongoing</span>'
    # The pill the check itself wears, so a reader scanning the list sorts
    # outages from slowdowns by a colour they have already learned.
    kind = incident["kind"]
    name = f'<span class="name">{_esc(incident["display"])}</span>' if named else ""
    return (
        f"<li>{name}"
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
        rows = "".join(_row(check, page, timezone) for check in group["checks"])
        groups.append(
            f'<section class="group"><h3>{_esc(group["name"])}</h3>'
            f'<div class="card">{rows}</div></section>'
        )

    # The section's heading is the filter: the log reaches as far as the
    # record does, and "recent" is a narrower question than "ever".
    rendered_at = parse_iso(state["generated_at"])
    recent = [
        i
        for i in state["incidents"]
        if in_window(i, rendered_at - timedelta(days=page["outage_log_days"]), rendered_at)
    ]
    if recent:
        items = "".join(_incident_item(i, timezone, named=True) for i in recent)
        incident_body = f'<ul class="log">{items}</ul>'
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

    script = _script(page["refresh_seconds"] * 3 * 1000)

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
            # How much of history_days this check was actually heard from.
            # The span itself is stated once, at the top level: it is the
            # page's, not this check's, and nine identical copies of one
            # number is a field that describes nothing.
            "observed_days": c["observed_days"],
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
            # How far back the record reaches: the span of every uptime
            # bar, of every availability figure, and of `incidents`.
            "history_days": state["page"]["history_days"],
            # Where the page draws the line under "Recent incidents".
            # Published so a consumer can reproduce that section rather
            # than guess at it; `incidents` itself is never narrowed to it.
            "recent_incident_days": state["page"]["outage_log_days"],
            "checks": checks,
            "incidents": incidents,
        },
        indent=2,
    )
