from datetime import datetime
from xml.etree import ElementTree

import badge
import fixtures


def state_with_overall(overall):
    return {"overall": overall}


class TestBadge:
    def test_width_is_computed_from_text_length(self):
        svg = badge.render_badge(state_with_overall("operational"))
        label_w = round(len("status") * badge.CHAR_WIDTH) + 2 * badge.PADDING
        message_w = round(len("operational") * badge.CHAR_WIDTH) + 2 * badge.PADDING
        root = ElementTree.fromstring(svg)
        assert root.attrib["width"] == str(label_w + message_w)

    def test_every_overall_state_renders_valid_svg(self):
        for overall, message in badge.MESSAGES.items():
            svg = badge.render_badge(state_with_overall(overall))
            root = ElementTree.fromstring(svg)
            assert root.attrib["role"] == "img"
            assert f"status: {message}" in svg

    def test_light_fills_carry_dark_text(self):
        assert 'fill="#3b2a00">degraded' in badge.render_badge(state_with_overall("degraded"))
        assert 'fill="#fff">major outage' in badge.render_badge(state_with_overall("major_outage"))

    def test_fixture_state_feeds_the_badge(self):
        svg = badge.render_badge(fixtures.build_state("one-down", datetime(2026, 8, 14)))
        assert "partial outage" in svg
