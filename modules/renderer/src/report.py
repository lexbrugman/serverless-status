"""What this run observed, reported back to Grafana as metrics.

The renderer holds the expected set of checks; Grafana holds only what
exists. So this is the one place that can tell a check that is failing
apart from a check that has stopped reporting at all — the second is
invisible to any query Grafana can run against itself.

Influx line protocol over plain HTTP on purpose: the handler ships as
stdlib plus boto3, and remote_write would mean protobuf and snappy in the
deployment package.
"""

import urllib.error
import urllib.parse
import urllib.request

MEASUREMENT = "status_page"
WRITE_PATH = "/api/v1/push/influx/write"


def payload(rendered_at: int, observed: dict[str, bool] | None) -> str:
    """The heartbeat always; the per-check gauges only when there was
    something to observe. A degraded run reached nothing, and reporting
    that as 'no check is publishing' would turn one Grafana outage into an
    alert per check."""
    lines = [f"{MEASUREMENT} rendered_timestamp={rendered_at}"]
    for job in sorted(observed or {}):
        lines.append(f"{MEASUREMENT},job={job} observed={1 if observed[job] else 0}")
    return "\n".join(lines)


def write_url(query_url: str) -> str:
    """The write endpoint beside the query one: same host, its own path."""
    parts = urllib.parse.urlsplit(query_url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, WRITE_PATH, "", ""))


def publish(sources: list[dict], body: str) -> list[str]:
    """Push to every account feeding the page, and report what failed
    rather than raising: the observer going quiet must never be what takes
    the page down."""
    failures = []
    for source in sources:
        # A source with no write credential is one there is nothing to
        # report to: the local dev stack has no Grafana behind it.
        if not source.get("write_token"):
            continue
        request = urllib.request.Request(
            write_url(source["query_url"]),
            data=body.encode(),
            headers={
                "Authorization": f"Bearer {source['user']}:{source['write_token']}",
                "Content-Type": "text/plain",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except (OSError, ValueError) as error:
            failures.append(f"{write_url(source['query_url'])}: {error}")
    return failures
