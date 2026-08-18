#!/usr/bin/env python3
"""Reject keys in config.yaml that nothing reads.

OpenTofu drops attributes an object type does not declare — silently, and
at plan time — so `latency_budget: 800` where the field is
`latency_budget_ms` gives a check with no budget and no complaint. The type
system rejects a missing required attribute and never an extra one, so a
typo is lost rather than reported.

Nothing here lists what is allowed. `tofu show -json` reports every
variable's type constraint already resolved into cty's JSON encoding, so
the declarations that own each part of the file are the schema and this
only walks the file against them. Adding a field anywhere changes nothing
in this script.

What is stated below is which declaration owns which part of the file —
its shape, not its contents.
"""

import json
import subprocess
import sys

# Where each top-level key's declaration lives: (module name prefix,
# variable). A prefix, because the checks module is one per account.
ROUTES = {
    "domain": ("renderer", "domain", False),
    "dns_zone_name": ("renderer", "dns_zone_name", False),
    "site": ("renderer", "site", False),
    "page": ("renderer", "page", False),
    "alerting": ("config", "alerting", False),
    "grafana_orgs": ("config", "grafana_orgs", False),
    # Each check is one element of the checks module's map, and reaches it
    # with the routing attributes already stripped.
    "checks": ("checks_", "checks", True),
}

# Consumed by wiring/routing and removed before the checks module sees a
# check, so their absence downstream is by design.
ROUTING_ATTRIBUTES = {"key", "grafana_org", "alert"}


def plan_json(root: str, plan: str) -> dict:
    shown = subprocess.run(
        ["tofu", f"-chdir={root}", "show", "-json", plan],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(shown.stdout)


def module_variables(plan: dict) -> dict:
    """Every module call's declared variables, keyed by call name."""
    calls = plan.get("configuration", {}).get("root_module", {}).get("module_calls", {})
    return {name: call.get("module", {}).get("variables", {}) for name, call in calls.items()}


def declared_for(variables: dict, prefix: str, name: str):
    for call, declared in variables.items():
        if (call == prefix or call.startswith(prefix)) and name in declared:
            return declared[name].get("type")
    return None


def attributes(constraint):
    """The attribute map of an object constraint, or None for anything else.

    cty encodes a type as a string for primitives, or a list whose head
    names the kind: ["object", {attr: type}, [optional]], ["list", type],
    ["map", type], ["set", type], ["tuple", [type, ...]].
    """
    if isinstance(constraint, list) and constraint and constraint[0] == "object":
        return constraint[1]
    return None


def element_of(constraint):
    """The element type of a collection, or None."""
    if isinstance(constraint, list) and constraint and constraint[0] in ("list", "set", "map"):
        return constraint[1]
    return None


def walk(value, constraint, path: str, ignore: set[str] | None = None) -> list[str]:
    """Every path in `value` that `constraint` does not declare.

    `dynamic` is cty's encoding of `any`, which declares nothing and so
    hides whatever is beneath it — those subtrees are reported as unchecked
    by main() rather than silently passed.
    """
    unknown = []
    declared = attributes(constraint)
    if declared is not None and isinstance(value, dict):
        for key, child in sorted(value.items()):
            if key in (ignore or set()):
                continue
            if key not in declared:
                unknown.append(f"{path}.{key}" if path else key)
                continue
            unknown += walk(child, declared[key], f"{path}.{key}" if path else key)
        return unknown

    element = element_of(constraint)
    if element is not None:
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                unknown += walk(child, element, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                unknown += walk(child, element, f"{path}[{index}]")
    return unknown


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else "tofu"
    plan_file = sys.argv[2] if len(sys.argv) > 2 else "tfplan"

    plan = plan_json(root, plan_file)
    outputs = plan.get("planned_values", {}).get("outputs", {})
    if "config_as_read" not in outputs:
        sys.exit(
            "ERROR: the plan carries no config_as_read output — this check reads the "
            "file through the same plan that typed it, and cannot run without it."
        )
    config = outputs["config_as_read"]["value"]
    variables = module_variables(plan)

    unknown, unchecked = [], []
    for key, value in sorted(config.items()):
        route = ROUTES.get(key)
        if route is None:
            unknown.append(key)
            continue
        prefix, name, per_element = route
        constraint = declared_for(variables, prefix, name)
        if constraint is None or constraint == "dynamic":
            unchecked.append(f"{key} (no type declaration reached it)")
            continue
        if per_element:
            for index, element in enumerate(value):
                unknown += walk(element, constraint, f"{key}[{index}]", ROUTING_ATTRIBUTES)
        else:
            unknown += walk(value, constraint, key)

    for level in unchecked:
        print(f"note: {level}")

    if unknown:
        sys.exit(
            "ERROR: config.yaml has keys nothing reads:\n  "
            + "\n  ".join(sorted(unknown))
            + "\n\nA key no declaration mentions is dropped rather than applied, so this"
            "\nwould have been a setting that silently did nothing. Check the spelling"
            "\nagainst docs/configuration.md, or remove it."
        )
    print(f"config.yaml: {len(config)} top-level keys, none unknown.")


if __name__ == "__main__":
    main()
