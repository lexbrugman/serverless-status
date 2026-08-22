import json
from datetime import datetime

import fixtures
import render
import state

NOW = datetime(2026, 8, 14, 12, 0, 0)


class TestHumanizeDuration:
    def test_bands(self):
        assert render.humanize_duration(None) == "ongoing"
        assert render.humanize_duration(45) == "45s"
        assert render.humanize_duration(300) == "5 min"
        assert render.humanize_duration(5400) == "1 h 30 min"
        assert render.humanize_duration(7200) == "2 h"
        assert render.humanize_duration(90000) == "1 d 1 h"
        assert render.humanize_duration(172800) == "2 d"


class TestLocalTime:
    def test_renders_in_site_timezone(self):
        assert render._local_time("2026-08-14T12:00:00Z", "Europe/Amsterdam") == (
            "14 Aug 2026, 14:00 CEST"
        )

    def test_short_time(self):
        assert render._short_time("2026-08-14T12:00:00Z", "Europe/Amsterdam") == "14 Aug 14:00"


class TestRenderPage:
    def test_all_green_page(self):
        page = render.render_page(fixtures.build_state("all-green", NOW, version="2026.814.0"))
        assert "All systems operational" in page
        assert 'class="banner b-operational"' in page
        assert "v2026.814.0" in page
        assert "www.example.com" in page
        assert 'data-rendered-at="2026-08-14T12:00:00Z"' in page
        assert '<meta http-equiv="refresh" content="60">' in page

    def test_the_footer_links_the_version_to_its_release(self):
        page = render.render_page(
            fixtures.build_state(
                "all-green", NOW, version="2026.814.0", repository="example/serverless-status"
            )
        )
        assert (
            '<a href="https://github.com/example/serverless-status/releases/tag/2026.814.0">'
            "serverless-status v2026.814.0</a>"
        ) in page

    def test_an_unpinned_page_links_to_the_repository_itself(self):
        """A root sourcing its modules from local paths names no release."""
        page = render.render_page(
            fixtures.build_state(
                "all-green", NOW, version="local", repository="example/serverless-status"
            )
        )
        assert '<a href="https://github.com/example/serverless-status">' in page
        assert "releases/tag" not in page

    def test_without_a_repository_the_version_is_plain_text(self):
        page = render.render_page(fixtures.build_state("all-green", NOW, version="2026.814.0"))
        assert "serverless-status v2026.814.0" in page
        assert "github.com" not in page

    def test_every_row_names_its_protocol(self):
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert '<span class="kind">https</span>' in page
        assert '<span class="kind">smtp</span>' in page
        assert '<span class="kind">ping</span>' in page

    def test_a_row_whose_address_adds_nothing_has_no_subtitle(self):
        """Two checks on one host are told apart by the protocol tag, so the
        subtitle is dropped rather than repeating the name."""
        built = fixtures.build_state("all-green", NOW)
        built["checks"][0]["subtitle"] = ""
        page = render.render_page(built)
        assert '<span class="sub"></span>' not in page

    def test_down_page_lists_the_outage_as_ongoing(self):
        page = render.render_page(fixtures.build_state("one-down", NOW))
        assert "Partial outage" in page
        assert 'class="dur open">ongoing</span>' in page

    def test_stale_cache_page_says_so(self):
        page = render.render_page(fixtures.build_state("stale-cache", NOW))
        assert "Live monitoring data is currently unavailable" in page
        assert "showing the last known state from 14 Aug 2026, 13:13 CEST" in page

    def test_degraded_without_snapshot_has_no_cached_timestamp(self):
        built = state.assemble(fixtures.manifest(), now=NOW, degraded=True)
        page = render.render_page(built)
        assert "showing the last known state.</div>" in page

    def test_optional_site_fields(self):
        mani = fixtures.manifest()
        mani["site"].update(
            {
                "title": "Custom title",
                "description": None,
                "logo_svg": '<svg viewBox="0 0 1 1"><rect width="1" height="1"/></svg>',
                "accent": None,
                "links": [],
            }
        )
        page = render.render_page(state.assemble(mani, now=NOW))
        assert "<title>Custom title</title>" in page
        assert 'class="desc"' not in page
        assert '<span class="logo">' in page
        assert "--accent:#16a34a" in page

    def test_title_defaults_to_site_name(self):
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert "<title>Example Corp status</title>" in page

    def test_missing_data_renders_placeholders(self):
        mani = fixtures.manifest()
        built = state.assemble(mani, now=NOW, degraded=True)
        page = render.render_page(built)
        assert ">— available</span>" in page
        assert "0 of 90 days observed" in page
        assert 'class="latency"' not in page
        assert 'class="spark"' not in page
        assert "No incidents in the last 30 days." in page

    def test_only_a_budgeted_check_states_its_compliance(self):
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert "within budget" in page
        assert "budget 800 ms" in page
        # One visible compliance line, for the one check that declared a
        # budget; the rest of the figures are behind the disclosure.
        assert page.count("within budget</span>") == 1
        assert page.count("<summary>detail</summary>") == 9

    def test_full_coverage_states_no_qualifier(self):
        """A window the page holds every day of needs none, and a note that
        appears regardless is a number that means nothing."""
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert "90 of 90 days observed" in page
        assert page.count("90 of 90 days observed") == 9
        assert "<span>90 days ago</span><span>today</span>" in page

    def test_a_slow_check_reads_slow(self):
        page = render.render_page(fixtures.build_state("degraded-slow", NOW))
        assert 'class="pill p-slow"' in page
        assert "Degraded performance" in page

    def test_the_figure_on_the_page_is_named_and_defined(self):
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert "availability · 24h: " in page
        assert "90 of 90 days observed" in page
        assert 'title="share of observed time with no confirmed outage' in page

    def test_probe_success_is_a_json_field_and_not_a_page_figure(self):
        """It counts executions, not time, so it moves when a minority of
        probe locations fails and nothing else on the page does. Beside a
        figure measured against the confirmed log it reads as a second
        opinion on the service; it is one on the instrument."""
        built = fixtures.build_state("all-green", NOW)
        assert "probe success" not in render.render_page(built)
        status = json.loads(render.render_status(built))
        assert all(c["probe_success_ratio"] is not None for c in status["checks"])

    def test_an_open_disclosure_survives_the_refresh(self):
        """The page reloads itself every refresh_seconds, and a browser
        restores scroll across that but not which <details> was open."""
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert 'data-key="website:detail"' in page
        assert "details[data-key]" in page
        assert "sessionStorage" in page

    def test_the_two_disclosures_on_a_row_cannot_collide(self):
        """A check key is a Prometheus job label, so it holds no colon;
        one namespace, and no check can be named into another's slot."""
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert 'data-key="docs:detail"' in page
        assert 'data-key="docs:incidents"' in page

    def test_a_row_discloses_its_own_incidents_with_the_count(self):
        """The docs outage is older than the page log but inside the bar,
        so the row is the only place it can be accounted for."""
        page = render.render_page(fixtures.build_state("all-green", NOW))
        assert "<summary>incidents (1)</summary>" in page
        # Named in the page log, where which check it was is the point;
        # unnamed in a row's, where the row has already said.
        assert page.count("<summary>detail</summary>") == 9
        assert page.count("<summary>incidents") == 3

    def test_the_section_shows_only_what_it_calls_recent(self):
        """The log reaches the record's ninety days; the section under
        'Recent incidents' is a view of it at outage_log_days, and the
        docs outage at 35 days is the one that separates the two."""
        built = fixtures.build_state("all-green", NOW)
        page = render.render_page(built)
        section = page.split('<section class="outages group">')[1]
        assert "docs" in {i["key"] for i in built["incidents"]}
        assert "Documentation" not in section

    def test_a_clean_check_carries_no_incident_disclosure(self):
        """Its bar is already saying so, and nine rows reading (0) is
        nine lines of nothing."""
        built = fixtures.build_state("all-green", NOW)
        clean = [c["key"] for c in built["checks"] if not c["incidents"]]
        assert clean
        page = render.render_page(built)
        for key in clean:
            assert f'data-key="{key}:incidents"' not in page


class TestRenderStatus:
    def test_schema_and_content(self):
        status = json.loads(render.render_status(fixtures.build_state("one-down", NOW)))
        assert status["schema_version"] == 3
        assert status["generated_at"] == "2026-08-14T12:00:00Z"
        assert status["degraded"] is False
        assert status["overall"] == "partial_outage"
        by_key = {c["key"]: c for c in status["checks"]}
        assert by_key["mail-inbound"]["state"] == "down"
        assert by_key["mail-inbound"]["type"] == "smtp"
        assert status["history_days"] == 90
        assert status["recent_incident_days"] == 30
        assert "window_days" not in by_key["website"]
        assert by_key["website"]["observed_days"] == 90
        assert [w["days"] for w in by_key["website"]["availability"]] == [1, 7, 30, 90]
        assert by_key["website"]["probe_success_ratio"] <= 1.0
        assert by_key["website"]["latency_budget_ms"] is None
        assert by_key["api"]["latency_budget_ms"] == 800
        assert [w["days"] for w in by_key["api"]["performance"]] == [1, 7, 30, 90]
        assert by_key["website"]["performance"] is None
        assert status["incidents"][0]["ended_at"] is None
        assert {i["kind"] for i in status["incidents"]} <= {"down", "slow"}
