"""The unknown-key guard over config.yaml.

The type encodings below are cty's, exactly as `tofu show -json` emits
them — an object is ["object", {attr: type}, [optional]], a collection is
["list"|"map"|"set", element]. The point of the guard is that nothing
restates the allowed keys, so these fixtures stand in for real
declarations rather than for a list somebody maintained.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "ci_check_config", ROOT / "template" / "bin" / "ci-check-config.py"
)
check_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_config)

SITE = [
    "object",
    {
        "name": "string",
        "timezone": "string",
        "links": ["list", ["object", {"label": "string", "url": "string"}]],
    },
    ["links"],
]

CHECK = [
    "object",
    {
        "display": "string",
        "type": "string",
        "host": "string",
        "latency_budget_ms": "number",
    },
    ["latency_budget_ms"],
]

ORGS = ["map", ["object", {"stack_slug": "string", "monthly_execution_budget": "number"}]]


class TestWalk:
    def test_a_correct_file_reports_nothing(self):
        value = {"name": "x", "timezone": "UTC", "links": [{"label": "a", "url": "u"}]}
        assert check_config.walk(value, SITE, "site") == []

    def test_an_unknown_key_is_named_with_its_path(self):
        assert check_config.walk({"name": "x", "tagline": "oops"}, SITE, "site") == ["site.tagline"]

    def test_it_descends_into_a_list_of_objects(self):
        """keys() cannot reach inside a list; this is the level an HCL guard
        would have had to be told about."""
        value = {"name": "x", "links": [{"label": "a", "url": "u"}, {"label": "b", "ur1": "u"}]}
        assert check_config.walk(value, SITE, "site") == ["site.links[1].ur1"]

    def test_it_descends_into_a_map_of_objects(self):
        value = {"acme": {"stack_slug": "s", "monthly_execution_budget": 1, "budgett": 2}}
        assert check_config.walk(value, ORGS, "grafana_orgs") == ["grafana_orgs.acme.budgett"]

    def test_an_optional_attribute_is_still_a_known_one(self):
        value = {"display": "API", "type": "https", "host": "a", "latency_budget_ms": 800}
        assert check_config.walk(value, CHECK, "checks[0]") == []

    def test_the_near_miss_this_exists_for(self):
        value = {"display": "API", "type": "https", "host": "a", "latency_budget": 800}
        assert check_config.walk(value, CHECK, "checks[0]") == ["checks[0].latency_budget"]

    def test_routing_attributes_are_not_unknown(self):
        """They are consumed and stripped before the checks module sees a
        check, so their absence downstream is by design."""
        value = {"display": "API", "type": "https", "host": "a", "grafana_org": "example"}
        assert check_config.walk(value, CHECK, "checks[0]", check_config.ROUTING_ATTRIBUTES) == []

    def test_a_dynamic_constraint_declares_nothing(self):
        """`any` hides whatever is beneath it, so a subtree behind one is
        reported as unchecked rather than passed silently."""
        assert check_config.walk({"anything": 1}, "dynamic", "checks") == []


class TestTypeEncoding:
    def test_object_attributes_are_read_from_the_cty_encoding(self):
        assert set(check_config.attributes(SITE)) == {"name", "timezone", "links"}

    def test_a_primitive_has_no_attributes(self):
        assert check_config.attributes("string") is None

    def test_collections_expose_their_element(self):
        assert check_config.element_of(ORGS) == ORGS[1]
        assert check_config.element_of(["set", "string"]) == "string"
        assert check_config.element_of("string") is None


class TestRoutes:
    def test_every_configurable_key_has_a_declaration_to_check_it_against(self):
        """A key with no route is reported unknown, so a new top-level key
        arriving without one fails loudly rather than going unchecked."""
        assert set(check_config.ROUTES) == {
            "domain",
            "dns_zone_name",
            "site",
            "page",
            "alerting",
            "grafana_orgs",
            "checks",
        }

    def test_the_checks_route_is_per_element(self):
        assert check_config.ROUTES["checks"][2] is True

    def test_declared_for_finds_a_per_account_module(self):
        variables = {"checks_acme": {"checks": {"type": ["map", CHECK]}}}
        assert check_config.declared_for(variables, "checks_", "checks") == ["map", CHECK]

    def test_declared_for_returns_none_when_nothing_declares_it(self):
        assert check_config.declared_for({}, "renderer", "site") is None


def test_the_template_config_passes_its_own_guard():
    """The shipped config.yaml must satisfy the schema it ships with."""
    import re

    text = (ROOT / "template" / "config.yaml").read_text()
    top_level = {match.group(1) for match in re.finditer(r"^([a-z_]+):", text, re.MULTILINE)}
    unknown = top_level - set(check_config.ROUTES)
    assert unknown == set(), f"config.yaml states keys with no declaration: {unknown}"


def test_it_refuses_a_plan_without_the_config_output(monkeypatch):
    monkeypatch.setattr(check_config, "plan_json", lambda *_: {"planned_values": {"outputs": {}}})
    monkeypatch.setattr("sys.argv", ["ci-check-config.py", "tofu", "tfplan"])
    with pytest.raises(SystemExit) as raised:
        check_config.main()
    assert "config_as_read" in str(raised.value)
