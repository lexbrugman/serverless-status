"""Colours, thresholds, and the SVG primitives shared by the page and badge.

The semantic palette is fixed, not configurable: a status page whose green is
configurable is a status page nobody can read at a glance. The four status
steps were validated for color-vision-deficiency separation and surface
contrast on both surfaces; the two entries that sit under 3:1 on the light
surface (warning, neutral) never appear without a label or tooltip — shape
and text carry every state, color only reinforces it.
"""

import html

# Colors keyed by role. Where light and dark mode need different steps the
# value is a (light, dark) pair; single values hold on both surfaces.
PALETTE = {
    "ok": "#0ca30c",
    "warn": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
    "neutral": ("#a8a29e", "#8a8a85"),
    # Text-weight variants for status-colored text on the light surface;
    # dark mode uses the fills directly (all clear 3:1 there).
    "ok_text": ("#006300", "#0ca30c"),
    "warn_text": ("#7a5200", "#fab219"),
    "critical_text": ("#b02f2f", "#d03b3b"),
    "surface": ("#fcfcfb", "#1a1a19"),
    "card": ("#ffffff", "#232322"),
    "border": ("#e7e5e4", "#3a3a38"),
    "ink": ("#1c1917", "#e7e5e4"),
    "ink_secondary": ("#57534e", "#a8a29e"),
    "ink_muted": ("#a8a29e", "#78716c"),
}

# Per-check states and the overall page states, each with its display label
# and palette roles for fill and text.
CHECK_STATES = {
    "up": {"label": "Operational", "fill": "ok", "text": "ok_text"},
    "slow": {"label": "Slow", "fill": "warn", "text": "warn_text"},
    "down": {"label": "Down", "fill": "critical", "text": "critical_text"},
    "unknown": {"label": "No data", "fill": "neutral", "text": "ink_secondary"},
}

# Two inks per state, because the two surfaces are held to different bars.
# The banner sets its label as large text, which clears at 3:1; the badge
# sets the same words at 11px, which does not — so a fill light enough to
# carry white on one is not light enough on the other. Stating both here
# keeps them one decision: the badge used to disagree with the banner about
# partial_outage, and drew white on a fill that could not hold it.
#
# Both are pinned by a test at the threshold that applies to them.
OVERALL_STATES = {
    "operational": {
        "label": "All systems operational",
        "fill": "ok",
        "banner_ink": "#ffffff",
        "badge_ink": "#052b05",
    },
    "degraded": {
        "label": "Degraded performance",
        "fill": "warn",
        "banner_ink": "#3b2a00",
        "badge_ink": "#3b2a00",
    },
    "partial_outage": {
        "label": "Partial outage",
        "fill": "serious",
        "banner_ink": "#3d1503",
        "badge_ink": "#3d1503",
    },
    "major_outage": {
        "label": "Major outage",
        "fill": "critical",
        "banner_ink": "#ffffff",
        "badge_ink": "#ffffff",
    },
    "partial_unknown": {
        "label": "Some checks are not reporting",
        "fill": "neutral",
        "banner_ink": "#1c1917",
        "badge_ink": "#1c1917",
    },
    "unknown": {
        "label": "Awaiting first data",
        "fill": "neutral",
        "banner_ink": "#1c1917",
        "badge_ink": "#1c1917",
    },
}


def banner_rules() -> str:
    """One CSS rule per overall state, from the same table the badge reads."""
    return "".join(
        f".b-{state}{{background:var(--{meta['fill']});color:{meta['banner_ink']}}}"
        for state, meta in OVERALL_STATES.items()
    )


# A day reads clean only at 100%: a single failed probe out of ~288 is
# exactly the kind of blip the bar exists to surface, and the amber step is
# where it surfaces. Below DAY_WARN — roughly seven minutes of a day — a
# confirmed outage is long enough to be the day's headline.
DAY_OK = 1.0
DAY_WARN = 0.995


def color(role: str, mode: str = "light") -> str:
    value = PALETTE[role]
    if isinstance(value, tuple):
        return value[0] if mode == "light" else value[1]
    return value


def css_variables(mode: str) -> str:
    """The palette as CSS custom property declarations for one mode."""
    return "".join(f"--{role.replace('_', '-')}:{color(role, mode)};" for role in PALETTE)


def day_state(day: dict) -> str:
    """The colour of one day in the bar.

    Every coloured step follows a confirmed period, written by the quorum
    over the window both states share. So no colour can be raised by a
    dissenting minority of probe locations or by a single sample, and none
    can contradict the figures beside it or the message the pager sent.
    Grey is time nobody observed, which is neither state.
    """
    if day["probe_ratio"] is None:
        return "unknown"
    if day["availability"] < DAY_WARN:
        return "down"
    if day["availability"] < DAY_OK:
        return "slow"
    if day["performance"] is not None and day["performance"] < DAY_OK:
        return "slow"
    return "up"


def uptime_bar(days: list[dict]) -> str:
    """One rect per day, newest right. Width derives from the viewBox so the
    bar scales with its container; each rect carries a <title> tooltip.
    """
    step, gap = 4, 1
    width = len(days) * step - gap
    rects = []
    for i, day in enumerate(days):
        state = day_state(day)
        if day["probe_ratio"] is None:
            tip = f"{day['date']} — no data"
        else:
            tip = (
                f"{day['date']} — {day['availability']:.2%} available, "
                f"{day['probe_ratio']:.2%} of probes succeeded"
            )
            if day["performance"] is not None:
                tip += f", {day['performance']:.2%} within budget"
        rects.append(
            f'<rect class="d-{state}" x="{i * step}" y="0" width="{step - gap}" height="28" '
            f'rx="1"><title>{html.escape(tip)}</title></rect>'
        )
    return (
        f'<svg class="bar" viewBox="0 0 {width} 28" preserveAspectRatio="none" '
        f'role="img" aria-label="daily availability, oldest to newest">{"".join(rects)}</svg>'
    )


def sparkline(
    points: list[float | None],
    width: int = 120,
    height: int = 28,
    budget_ms: float | None = None,
) -> str:
    """A single path over the 24h latency series. No axes; it is a shape,
    not a chart — except where a budget is declared, which is the one level
    the shape has to be read against.

    A series normalised to its own maximum fills the box whatever its
    magnitude, so a slow day and a fast day draw identically. Scaling to
    the budget instead is what makes the distance to it visible, and the
    guide line is where the amber state begins.
    """
    values = [v for v in points if v is not None]
    if len(values) < 2:
        return ""
    top = max(values)
    if budget_ms is not None:
        top = max(top, budget_ms)
    top = top or 1.0
    pad = 2
    span = height - 2 * pad
    coords = []
    n = len(points)
    for i, v in enumerate(points):
        if v is None:
            continue
        x = i * width / (n - 1)
        y = pad + span * (1 - v / top)
        coords.append(f"{x:.1f},{y:.1f}")
    path = "M" + " L".join(coords)
    guide = ""
    label = "24-hour latency"
    if budget_ms is not None:
        edge = pad + span * (1 - budget_ms / top)
        guide = f'<line class="spark-budget" x1="0" y1="{edge:.1f}" x2="{width}" y2="{edge:.1f}"/>'
        label = f"24-hour latency against a {budget_ms:.0f} ms budget"
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{label}">'
        f'<line class="spark-base" x1="0" y1="{height - 1}" x2="{width}" y2="{height - 1}"/>'
        f'{guide}<path d="{path}" fill="none"/></svg>'
    )


def state_glyph(state: str) -> str:
    """A small shape that carries the state alongside its color, so the pill
    survives color-blindness and greyscale printing.
    """
    shapes = {
        "up": '<circle cx="5" cy="5" r="4"/>',
        "slow": '<path d="M5 1 L9.5 9 L0.5 9 Z"/>',
        "down": (
            '<path d="M1.5 1.5 L8.5 8.5 M8.5 1.5 L1.5 8.5" stroke-width="2.6" '
            'stroke="currentColor" fill="none" stroke-linecap="round"/>'
        ),
        "unknown": (
            '<circle cx="5" cy="5" r="3.4" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        ),
    }
    return f'<svg class="glyph" viewBox="0 0 10 10" aria-hidden="true">{shapes[state]}</svg>'


def favicon_data_uri(overall: str) -> str:
    """An inline SVG dot colored by overall state, so the browser tab answers
    the question before the page does.
    """
    fill = color(OVERALL_STATES[overall]["fill"], "light")
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
        f"<circle cx='8' cy='8' r='7' fill='{fill}'/></svg>"
    )
    return "data:image/svg+xml," + svg.replace("<", "%3C").replace(">", "%3E").replace("#", "%23")
