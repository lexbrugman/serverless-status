#!/usr/bin/env python3
"""Step zero, verified from CI: the SMTP checks are the reason this design
exists, and they are the one thing OpenTofu cannot prove. Two assertions
no plan, state, or mock can make.

The dialogue as the backend stores it is what the probes execute — the
provider's transmission is guarded upstream (scripts/check-sm-payloads.py
in the public repository), the backend's storage only by asking it. And a
published probe_success sample proves the checks are deployed and their
probes are running.

What the sample says is not a gate. A page whose subject is down must
still deploy — reporting that is its job — and no metric distinguishes a
blocked port from a server that is simply refusing today. So a failing
check is reported for a human to judge, and only a check that never
reports at all stops the run.
"""

import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# One check frequency is 5 minutes; this waits for two, so a probe that
# runs late still lands inside the window.
DEADLINE_SECONDS = 12 * 60
POLL_SECONDS = 30


def walk(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from walk(child)


def decoded(value):
    return base64.b64decode(value or "").decode(errors="replace")


def get(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def state_resources():
    shown = subprocess.run(["tofu", "show", "-json"], capture_output=True, text=True, check=True)
    state = json.loads(shown.stdout)
    return list(walk(state.get("values", {}).get("root_module", {})))


def state_dialogues(resources):
    """Every smtp check's dialogue as the provider read it back."""
    dialogues = {}
    for resource in resources:
        if resource["type"] != "grafana_synthetic_monitoring_check":
            continue
        if ".smtp[" not in resource["address"]:
            continue
        tcp = resource["values"]["settings"][0]["tcp"][0]
        dialogues[resource["values"]["job"]] = [
            {
                "expect": entry.get("expect") or "",
                "send": entry.get("send") or "",
                "start_tls": bool(entry.get("start_tls")),
            }
            for entry in tcp.get("query_response") or []
        ]
    return dialogues


def stored_dialogues(resources):
    """Every tcp check's dialogue as the SM API stores it."""
    dialogues = {}
    for resource in resources:
        if resource["type"] != "grafana_synthetic_monitoring_installation":
            continue
        url = resource["values"]["stack_sm_api_url"].rstrip("/")
        token = resource["values"]["sm_access_token"]
        for check in get(f"{url}/api/v1/check/list", {"Authorization": f"Bearer {token}"}):
            tcp = check.get("settings", {}).get("tcp")
            if not tcp:
                continue
            dialogues[check["job"]] = [
                {
                    "expect": decoded(entry.get("expect")),
                    "send": decoded(entry.get("send")),
                    "start_tls": bool(entry.get("startTLS", False)),
                }
                for entry in tcp.get("queryResponse") or []
            ]
    return dialogues


def show(title, dialogue):
    print(f"== {title}")
    for i, entry in enumerate(dialogue):
        print(
            f"  {i}: expect={entry['expect']!r}"
            f" send={entry['send']!r}"
            f" start_tls={entry['start_tls']}"
        )


def compare_dialogues(state, stored):
    """The backend must keep every entry the provider sent it. Order is not
    asserted here — probe_success is the live proof of that, and it is the
    only proof that counts."""
    failures = []
    for job, declared in sorted(state.items()):
        show(f"{job}: as the provider read it back", declared)
        arrived = stored.get(job)
        if arrived is None:
            failures.append(f"{job}: the SM API stores no dialogue for this check")
            continue
        show(f"{job}: as the SM API stores it", arrived)
        key = sorted(json.dumps(entry, sort_keys=True) for entry in declared)
        if key != sorted(json.dumps(entry, sort_keys=True) for entry in arrived):
            failures.append(
                f"{job}: the stored dialogue is not the one that was sent — "
                f"{len(declared)} entries sent, {len(arrived)} stored (printed above)"
            )
    return failures


def prometheus_credentials(resources):
    query_url = user = token = None
    for resource in resources:
        values = resource["values"]
        if resource["type"] == "grafana_cloud_stack" and resource.get("mode") == "data":
            query_url = f"{values['prometheus_url']}/api/prom"
            user = str(values["prometheus_user_id"])
        if (
            resource["type"] == "grafana_cloud_access_policy_token"
            and resource["name"] == "metrics_read"
        ):
            token = values["token"]
    return query_url, user, token


def probe_results(query_url, auth, jobs):
    """probe_success per job, absent while no probe has published yet."""
    selector = "|".join(jobs)
    query = urllib.parse.quote(f'probe_success{{job=~"{selector}"}}')
    try:
        response = get(f"{query_url}/api/v1/query?query={query}", {"Authorization": auth})
    except urllib.error.HTTPError as error:
        # Freshly minted read credentials can lag their first use.
        print(f"  (Prometheus returned {error.code}; retrying)")
        return {}
    results = {}
    for series in response.get("data", {}).get("result", []):
        results[series["metric"]["job"]] = float(series["value"][1])
    return results


def await_probes(query_url, user, token, jobs):
    """Wait until every check has published a sample. Its value is reported,
    never required."""
    auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()
    deadline = time.monotonic() + DEADLINE_SECONDS
    while True:
        results = probe_results(query_url, auth, jobs)
        silent = [job for job in jobs if job not in results]
        if not silent:
            for job in sorted(results):
                print(f"  {job}: probe_success={results[job]:g}")
            failing = sorted(job for job, value in results.items() if value == 0)
            if failing:
                print(
                    "\nReporting failure: "
                    + ", ".join(failing)
                    + "\nThe page will show these as down, which is correct if they are."
                    + " If they should be up, the probe's own log in the Synthetic"
                    + " Monitoring UI shows how far the conversation got — for smtp,"
                    + " a probe that cannot egress port 25 never gets a greeting."
                )
            return []
        remaining = max(int(deadline - time.monotonic()), 0)
        print(f"  waiting for a first sample from {len(silent)} check(s), {remaining}s left")
        if time.monotonic() >= deadline:
            return [f"{job}: no probe_success sample published" for job in silent]
        time.sleep(POLL_SECONDS)


def main():
    # A CI log is a pipe, and a pipe is block-buffered: without this the
    # dialogue and every poll line stay invisible until the step ends,
    # which is exactly when they stop being useful.
    sys.stdout.reconfigure(line_buffering=True)

    resources = state_resources()
    state = state_dialogues(resources)
    if not state:
        print("No smtp checks configured; step zero has nothing to prove.")
        return

    failures = compare_dialogues(state, stored_dialogues(resources))

    query_url, user, token = prometheus_credentials(resources)
    if not all((query_url, user, token)):
        failures.append("no Prometheus read credentials in state — cannot read probe results")
    elif not failures:
        print(f"== awaiting a first sample from {len(state)} smtp check(s)")
        failures += await_probes(query_url, user, token, sorted(state))

    if failures:
        sys.exit(
            "ERROR: step zero failed — nothing downstream is built until it passes:\n  "
            + "\n  ".join(failures)
            + "\n\nA check that never publishes is not running: it exists in Grafana but no"
            "\nprobe executes it, which no amount of downstream infrastructure fixes."
        )

    print("Step zero passed: the dialogue survived storage and every check is publishing.")


if __name__ == "__main__":
    main()
