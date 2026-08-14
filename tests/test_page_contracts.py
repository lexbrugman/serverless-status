"""The page-level contracts: well-formed output, the zero-external-dependency
rule, and visible staleness — asserted over every fixture state."""

from datetime import datetime

import badge
import fixtures
import preview
import pytest
import render

NOW = datetime(2026, 8, 14, 12, 0, 0)


@pytest.fixture(params=fixtures.STATES)
def built(request):
    return fixtures.build_state(request.param, NOW, version="2026.814.0")


class TestEveryFixtureState:
    def test_html_is_well_formed(self, built):
        assert preview.validate_html(render.render_page(built)) == []

    def test_no_external_references_outside_site_links(self, built):
        allowed = {link["url"] for link in built["site"]["links"]}
        page = render.render_page(built)
        assert preview.external_references(page, allowed) == []
        assert preview.external_references(render.render_status(built), allowed) == []
        assert preview.external_references(badge.render_badge(built), set()) == []

    def test_status_json_matches_the_schema(self, built):
        assert preview.validate_status(render.render_status(built)) == []

    def test_badge_parses(self, built):
        assert preview.validate_badge(badge.render_badge(built)) == []

    def test_staleness_is_visible(self, built):
        page = render.render_page(built)
        assert 'data-rendered-at="2026-08-14T12:00:00Z"' in page
        # refresh_seconds * 3, in milliseconds — the client-side threshold.
        assert "180000" in page
        assert 'id="stale"' in page


class TestValidatorsThemselves:
    def test_broken_html_is_caught(self):
        errors = preview.validate_html("<!DOCTYPE html><html><main><div></main></html>")
        assert any("closing </main>" in e for e in errors)

    def test_external_reference_is_caught(self):
        assert preview.external_references("see https://evil.example/x", set()) == [
            "https://evil.example/x"
        ]

    def test_svg_namespace_is_not_external(self):
        assert preview.external_references("xmlns='http://www.w3.org/2000/svg'", set()) == []
