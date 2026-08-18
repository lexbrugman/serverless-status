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
        assert '<span class="ratio">—</span>' in page
        assert 'class="latency"' not in page
        assert 'class="spark"' not in page
        assert "No outages in the last 30 days." in page


class TestRenderStatus:
    def test_schema_and_content(self):
        status = json.loads(render.render_status(fixtures.build_state("one-down", NOW)))
        assert status["schema_version"] == 1
        assert status["generated_at"] == "2026-08-14T12:00:00Z"
        assert status["degraded"] is False
        assert status["overall"] == "partial_outage"
        by_key = {c["key"]: c for c in status["checks"]}
        assert by_key["mail-inbound"]["state"] == "down"
        assert by_key["mail-inbound"]["type"] == "smtp"
        assert by_key["website"]["uptime_window_days"] == 90
        assert status["outages"][0]["ended_at"] is None
