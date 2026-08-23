#!/usr/bin/env python3
"""Render every fixture state to out/ and validate the results — no
credentials, no network, no container. This is the loop for iterating on the
SVG and CSS, and what the render-checks CI job uploads for review.

Usage: preview.py [--check] [--serve [PORT]] [--out DIR]
"""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "modules" / "renderer" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import badge  # noqa: E402
import fixtures  # noqa: E402
import render  # noqa: E402

# The SVG namespace is an identifier, never fetched; everything else with a
# scheme must come from the configured site.links.
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

# What the preview renders as the page's origin; instances derive theirs
# from their module pin.
SOURCE_REPOSITORY = "lexbrugman/serverless-status"

VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


class _WellFormedChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.seen = set()

    def handle_starttag(self, tag, attrs):
        self.seen.add(tag)
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"closing </{tag}> with nothing open")
        elif self.stack[-1] != tag:
            self.errors.append(f"closing </{tag}> while <{self.stack[-1]}> is open")
        else:
            self.stack.pop()


def validate_html(document: str) -> list[str]:
    """Well-formedness errors, empty when the page is sound."""
    checker = _WellFormedChecker()
    checker.feed(document)
    checker.close()
    errors = list(checker.errors)
    if checker.stack:
        errors.append(f"unclosed tags at end of document: {checker.stack}")
    for required in ("html", "title", "main", "footer"):
        if required not in checker.seen:
            errors.append(f"missing <{required}>")
    if not document.lstrip().startswith("<!DOCTYPE html>"):
        errors.append("missing doctype")
    return errors


def external_references(text: str, allowed: set[str]) -> list[str]:
    """Every http(s) URL in the text that is not explicitly allowed."""
    found = re.findall(r"https?://[^\s\"'<>)]+", text)
    return [url for url in found if url not in allowed and url != SVG_NAMESPACE]


def validate_status(document: str) -> list[str]:
    errors = []
    payload = json.loads(document)
    for field, kind in [
        ("schema_version", int),
        ("generated_at", str),
        ("degraded", bool),
        ("overall", str),
        # The two spans a consumer needs to read the rest: what the record
        # covers, and where the page calls an incident recent.
        ("history_days", int),
        ("recent_incident_days", int),
        ("checks", list),
        ("incidents", list),
    ]:
        if not isinstance(payload.get(field), kind):
            errors.append(f"status.json {field} missing or not {kind.__name__}")
    for check in payload.get("checks", []):
        for field in ("key", "display", "group", "state", "availability", "observed_days"):
            if field not in check:
                errors.append(f"status.json check missing {field}")
    return errors


def validate_badge(document: str) -> list[str]:
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as error:
        return [f"badge.svg does not parse: {error}"]
    if not root.tag.endswith("svg"):
        return ["badge.svg root element is not <svg>"]
    return []


def render_fixture(name: str, now: datetime, version: str | None) -> dict[str, str]:
    state = fixtures.build_state(name, now, version, repository=SOURCE_REPOSITORY)
    allowed = {link["url"] for link in state["site"].get("links") or []}
    # The footer's own link is the one external reference the page may
    # carry: an anchor to what built it, never a resource it loads.
    allowed.add(f"https://github.com/{SOURCE_REPOSITORY}")
    if version:
        allowed.add(f"https://github.com/{SOURCE_REPOSITORY}/releases/tag/{version}")
    page = render.render_page(state)
    status = render.render_status(state)
    badge_svg = badge.render_badge(state)

    errors = validate_html(page)
    errors += validate_status(status)
    errors += validate_badge(badge_svg)
    for document, allowed_urls, where in [
        (page, allowed, "index.html"),
        (status, allowed, "status.json"),
        (badge_svg, set(), "badge.svg"),
    ]:
        for url in external_references(document, allowed_urls):
            errors.append(f"external reference in {where}: {url}")
    if errors:
        raise SystemExit(f"ERROR: fixture {name} failed validation:\n  " + "\n  ".join(errors))

    return {"index.html": page, "status.json": status, "badge.svg": badge_svg}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    parser.add_argument("--serve", nargs="?", const=0, type=int, metavar="PORT")
    parser.add_argument("--out", default=str(ROOT / "out"), metavar="DIR")
    args = parser.parse_args()
    if args.check and args.serve is not None:
        parser.error("--check writes nothing to serve; drop one of the flags")

    now = datetime.now(UTC).replace(tzinfo=None)
    out = Path(args.out)

    index_links = []
    for name in fixtures.STATES:
        documents = render_fixture(name, now, version="preview")
        if not args.check:
            target = out / name
            target.mkdir(parents=True, exist_ok=True)
            for filename, content in documents.items():
                (target / filename).write_text(content)
        index_links.append(f'<li><a href="{name}/index.html">{name}</a></li>')
        print(f"{name}: ok")

    if not args.check:
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            "<title>fixture previews</title></head>"
            f"<body><h1>Fixture states</h1><ul>{''.join(index_links)}</ul></body></html>"
        )
        print(f"rendered to {out}/")

    if args.serve is not None:
        import functools
        import http.server

        # Inside the toolbox, bootstrap-shell.sh forwards BOOTSTRAP_PUBLISH:
        # the port must match the published one, and the bind must cover the
        # container address the mapping forwards to (its loopback would be
        # unreachable). A bare host run stays loopback-only.
        publish = os.environ.get("BOOTSTRAP_PUBLISH")
        port = args.serve or (int(publish) if publish else 8000)
        bind = "0.0.0.0" if publish else "127.0.0.1"
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
        print(f"serving {out} on http://localhost:{port}/")
        http.server.ThreadingHTTPServer((bind, port), handler).serve_forever()


if __name__ == "__main__":
    main()
