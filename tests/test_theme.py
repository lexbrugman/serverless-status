import theme


class TestColors:
    def test_mode_pairs_resolve_per_mode(self):
        assert theme.color("surface", "light") == "#fcfcfb"
        assert theme.color("surface", "dark") == "#1a1a19"

    def test_single_values_hold_in_both_modes(self):
        assert theme.color("ok", "light") == theme.color("ok", "dark") == "#0ca30c"

    def test_css_variables_cover_every_role(self):
        light = theme.css_variables("light")
        for role in theme.PALETTE:
            assert f"--{role.replace('_', '-')}:" in light


class TestDayState:
    def test_thresholds(self):
        assert theme.day_state(None) == "unknown"
        assert theme.day_state(1.0) == "up"
        assert theme.day_state(0.999) == "slow"
        assert theme.day_state(0.995) == "slow"
        assert theme.day_state(0.99) == "down"


class TestUptimeBar:
    def test_one_rect_per_day_with_tooltips(self):
        days = [
            {"date": "2026-08-12", "ratio": 1.0},
            {"date": "2026-08-13", "ratio": None},
            {"date": "2026-08-14", "ratio": 0.9931},
        ]
        bar = theme.uptime_bar(days)
        assert bar.count("<rect") == 3
        assert 'class="d-up"' in bar and 'class="d-unknown"' in bar and 'class="d-down"' in bar
        assert "<title>2026-08-13 — no data</title>" in bar
        assert "<title>2026-08-14 — 99.31%</title>" in bar


class TestSparkline:
    def test_fewer_than_two_points_renders_nothing(self):
        assert theme.sparkline([]) == ""
        assert theme.sparkline([1.0, None]) == ""

    def test_path_normalises_to_series_max(self):
        svg = theme.sparkline([0.0, 100.0], width=100, height=28)
        assert svg.startswith('<svg class="spark"')
        assert 'd="M0.0,26.0 L100.0,2.0"' in svg

    def test_gaps_are_skipped_not_zeroed(self):
        svg = theme.sparkline([100.0, None, 100.0])
        assert svg.count("L") == 1

    def test_all_zero_series_does_not_divide_by_zero(self):
        assert "NaN" not in theme.sparkline([0.0, 0.0])


class TestGlyphsAndFavicon:
    def test_every_state_has_a_distinct_glyph(self):
        glyphs = {state: theme.state_glyph(state) for state in theme.CHECK_STATES}
        assert len(set(glyphs.values())) == 4

    def test_favicon_is_a_data_uri_in_the_overall_color(self):
        uri = theme.favicon_data_uri("major_outage")
        assert uri.startswith("data:image/svg+xml,")
        assert "%23d03b3b" in uri
        assert "<" not in uri and ">" not in uri
