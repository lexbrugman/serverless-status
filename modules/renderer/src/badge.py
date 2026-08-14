"""Pure badge rendering: state dict in, shields-style SVG out.

Fixed width computed from text length; no external font, no external shield
service — the badge obeys the same zero-dependency rule as the page.
"""

import theme

MESSAGES = {
    "operational": "operational",
    "degraded": "degraded",
    "partial_outage": "partial outage",
    "major_outage": "major outage",
    "unknown": "unknown",
}

LABEL = "status"
LABEL_FILL = "#555"
# Light fills (warn, neutral) need dark text; the rest carry white.
DARK_TEXT = {"degraded": "#3b2a00", "unknown": "#1c1917"}

FONT_SIZE = 11
# Average glyph advance for the system sans fonts badges render in at 11px;
# the width test pins the arithmetic, not the fonts.
CHAR_WIDTH = 6.1
PADDING = 10
HEIGHT = 20


def _segment_width(text: str) -> int:
    return round(len(text) * CHAR_WIDTH) + 2 * PADDING


def render_badge(state: dict) -> str:
    overall = state["overall"]
    message = MESSAGES[overall]
    fill = theme.color(theme.OVERALL_STATES[overall]["fill"], "light")
    text_fill = DARK_TEXT.get(overall, "#fff")

    label_w = _segment_width(LABEL)
    message_w = _segment_width(message)
    total = label_w + message_w

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="{HEIGHT}" \
role="img" aria-label="{LABEL}: {message}">
<title>{LABEL}: {message}</title>
<clipPath id="r"><rect width="{total}" height="{HEIGHT}" rx="3"/></clipPath>
<g clip-path="url(#r)">
<rect width="{label_w}" height="{HEIGHT}" fill="{LABEL_FILL}"/>
<rect x="{label_w}" width="{message_w}" height="{HEIGHT}" fill="{fill}"/>
</g>
<g text-anchor="middle" font-family="Verdana,Geneva,sans-serif" font-size="{FONT_SIZE}">
<text x="{label_w / 2}" y="14" fill="#fff">{LABEL}</text>
<text x="{label_w + message_w / 2}" y="14" fill="{text_fill}">{message}</text>
</g>
</svg>
"""
