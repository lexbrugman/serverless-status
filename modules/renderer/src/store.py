"""DynamoDB reads and writes; every item shape lives here.

One table, three item kinds: the SITE/LATEST snapshot (overwritten every
run), daily rollups (atomic ADD so retries cannot double-count), and outage
records written on transition — the data *is* the incident log.
"""

from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

LATEST_PK = "SITE"
LATEST_SK = "LATEST"


def table(name: str, endpoint_url: str | None = None):
    resource = boto3.resource("dynamodb", endpoint_url=endpoint_url)
    return resource.Table(name)


def _plain(value):
    """boto3 returns numbers as Decimal; the renderer wants ints and floats."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if value.__class__.__name__ == "Decimal":
        return int(value) if value == int(value) else float(value)
    return value


def get_latest(tbl) -> dict | None:
    item = tbl.get_item(Key={"PK": LATEST_PK, "SK": LATEST_SK}).get("Item")
    if not item:
        return None
    return {
        "rendered_at": item["rendered_at"],
        "source": item.get("source"),
        "degraded": bool(item.get("degraded")),
        "checks": _plain(item["checks"]),
    }


def put_latest(tbl, snapshot: dict, source: str, degraded: bool) -> None:
    tbl.put_item(
        Item={
            "PK": LATEST_PK,
            "SK": LATEST_SK,
            "rendered_at": snapshot["rendered_at"],
            "source": source,
            "degraded": degraded,
            "checks": snapshot["checks"],
        }
    )


def update_rollup(
    tbl, key: str, day: str, up: bool, latency_ms: int | None, expires_at: int
) -> None:
    """Fold one sample into the day's rollup with an atomic ADD, then raise
    latency_max under a condition — concurrent or retried invocations cannot
    double-count incorrectly."""
    latency = latency_ms or 0
    tbl.update_item(
        Key={"PK": f"CHECK#{key}", "SK": f"DAY#{day}"},
        UpdateExpression=("ADD samples :one, successes :s, latency_sum :l SET expires_at = :exp"),
        ExpressionAttributeValues={
            ":one": 1,
            ":s": 1 if up else 0,
            ":l": latency,
            ":exp": expires_at,
        },
    )
    try:
        tbl.update_item(
            Key={"PK": f"CHECK#{key}", "SK": f"DAY#{day}"},
            UpdateExpression="SET latency_max = :l",
            ConditionExpression="attribute_not_exists(latency_max) OR latency_max < :l",
            ExpressionAttributeValues={":l": latency},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def rollups(tbl, key: str, first_day: str, last_day: str) -> list[dict]:
    response = tbl.query(
        KeyConditionExpression=Key("PK").eq(f"CHECK#{key}")
        & Key("SK").between(f"DAY#{first_day}", f"DAY#{last_day}")
    )
    return [
        {
            "date": item["SK"].removeprefix("DAY#"),
            "samples": _plain(item["samples"]),
            "successes": _plain(item["successes"]),
            "latency_sum": _plain(item.get("latency_sum", 0)),
            "latency_max": _plain(item.get("latency_max", 0)),
        }
        for item in response["Items"]
    ]


def open_outage(tbl, key: str, started_at: str, expires_at: int) -> None:
    tbl.put_item(
        Item={
            "PK": f"CHECK#{key}",
            "SK": f"OUTAGE#{started_at}",
            "started_at": started_at,
            "expires_at": expires_at,
        }
    )


def close_outage(tbl, key: str, ended_at: str) -> None:
    """Close the newest still-open outage, deriving the duration from the
    record's own started_at. A missing open record (first run after a
    redeploy, or a transition seen twice) is not an error — there is simply
    nothing to close."""
    response = tbl.query(
        KeyConditionExpression=Key("PK").eq(f"CHECK#{key}") & Key("SK").begins_with("OUTAGE#"),
        ScanIndexForward=False,
        Limit=5,
    )
    for item in response["Items"]:
        if "ended_at" not in item:
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            duration = int(
                (
                    datetime.strptime(ended_at, fmt) - datetime.strptime(item["started_at"], fmt)
                ).total_seconds()
            )
            tbl.update_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET ended_at = :e, duration_seconds = :d",
                ExpressionAttributeValues={":e": ended_at, ":d": duration},
            )
            return


def outages(tbl, key: str) -> list[dict]:
    """Every outage record for the check (TTL bounds the set). Windowing is
    the assembly's job: an ongoing outage older than the log window must
    still surface, so the read cannot pre-filter by start time."""
    response = tbl.query(
        KeyConditionExpression=Key("PK").eq(f"CHECK#{key}") & Key("SK").begins_with("OUTAGE#"),
    )
    return [
        {
            "started_at": item["started_at"],
            "ended_at": item.get("ended_at"),
            "duration_seconds": _plain(item.get("duration_seconds")),
        }
        for item in response["Items"]
    ]
