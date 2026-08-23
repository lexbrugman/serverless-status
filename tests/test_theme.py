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


def _day(
    date: str,
    probe_ratio: float | None,
    availability: float | None,
    performance: float | None = None,
) -> dict:
    return {
        "date": date,
        "probe_ratio": probe_ratio,
        "availability": availability,
        "performance": performance,
    }


class TestDayState:
    def test_a_day_nobody_observed_is_grey(self):
        assert theme.day_state(_day("2026-08-14", None, None)) == "unknown"

    def test_a_confirmed_outage_leads_the_day(self):
        assert theme.day_state(_day("2026-08-14", 0.99, 0.99)) == "down"

    def test_a_brief_outage_reads_amber(self):
        assert theme.day_state(_day("2026-08-14", 1.0, 0.999)) == "slow"

    def test_probe_noise_the_log_never_confirmed_does_not_colour_the_day(self):
        """A dissenting minority of probe locations reaches no record, so it
        reaches no colour either."""
        assert theme.day_state(_day("2026-08-14", 0.996, 1.0)) == "up"

    def test_a_confirmed_degradation_reads_amber(self):
        assert theme.day_state(_day("2026-08-14", 1.0, 1.0, 0.98)) == "slow"

    def test_a_clean_day_is_green(self):
        assert theme.day_state(_day("2026-08-14", 1.0, 1.0)) == "up"
        assert theme.day_state(_day("2026-08-14", 1.0, 1.0, 1.0)) == "up"


class TestUptimeBar:
    def test_one_rect_per_day_with_tooltips(self):
        days = [
            _day("2026-08-12", 1.0, 1.0),
            _day("2026-08-13", None, None),
            _day("2026-08-14", 0.9931, 0.98, 0.95),
        ]
        bar = theme.uptime_bar(days)
        assert bar.count("<rect") == 3
        assert 'class="d-up"' in bar and 'class="d-unknown"' in bar and 'class="d-down"' in bar
        assert "<title>2026-08-13 — no data</title>" in bar
        assert (
            "<title>2026-08-14 — 98.00% available, 99.31% of probes succeeded, "
            "95.00% within budget</title>" in bar
        )


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

    def test_a_budget_scales_the_series_and_draws_its_guide(self):
        """A self-normalised series fills the box whatever its magnitude, so
        the level only becomes readable against a declared budget."""
        svg = theme.sparkline([100.0, 200.0], width=100, height=28, budget_ms=400.0)
        assert 'class="spark-budget"' in svg and 'y1="2.0"' in svg
        assert 'd="M0.0,20.0 L100.0,14.0"' in svg
        assert 'aria-label="24-hour latency against a 400 ms budget"' in svg

    def test_a_series_past_its_budget_crosses_the_guide(self):
        svg = theme.sparkline([100.0, 800.0], budget_ms=400.0)
        assert 'y1="14.0"' in svg

    def test_without_a_budget_there_is_no_guide(self):
        assert "spark-budget" not in theme.sparkline([1.0, 2.0])

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


def _luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestBannerInk:
    """Every overall state is drawn as a filled block with words on it, on
    the page and alone in the badge. A badge carries no label or tooltip
    beside it, so its contrast is the whole of what it says."""

    def test_every_state_clears_the_text_threshold(self):
        for state, meta in theme.OVERALL_STATES.items():
            ratio = _contrast(theme.color(meta["fill"], "light"), meta["on_fill"])
            assert ratio >= 4.5, f"{state}: {ratio:.2f}:1 on {meta['fill']}"

    def test_the_banner_css_comes_from_the_same_table(self):
        """The page and the badge disagreed about partial_outage until both
        read this; nothing should be able to set one without the other."""
        rules = theme.banner_rules()
        for state, meta in theme.OVERALL_STATES.items():
            assert (
                f".b-{state}{{background:var(--{meta['fill']});color:{meta['on_fill']}}}" in rules
            )

    def test_the_check_states_it_covers(self):
        assert set(theme.OVERALL_STATES) == {
            "operational",
            "degraded",
            "partial_outage",
            "major_outage",
            "partial_unknown",
            "unknown",
        }
