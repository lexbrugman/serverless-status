#!/usr/bin/env python3
"""Step zero, verified from CI: the SMTP checks are the reason this design
exists, and they are the one thing OpenTofu cannot prove. Two assertions
no plan, state, or mock can make.

The dialogue as the backend stores it is what the probes execute — the
provider's transmission is guarded upstream (scripts/check-sm-payloads.py
in the public repository), the backend's storage only by asking it. And
probe_success reaching 1 proves what nothing offline can: that the probes
egress port 25 at all, and that the STARTTLS upgrade completes in order —
a scrambled conversation times out instead of reporting green.

Nothing downstream is built until both hold.
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
    auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()
    deadline = time.monotonic() + DEADLINE_SECONDS
    while True:
        results = probe_results(query_url, auth, jobs)
        pending = [job for job in jobs if job not in results]
        failing = [job for job in jobs if results.get(job) == 0]
        if not pending and not failing:
            for job in jobs:
                print(f"  {job}: probe_success=1")
            return []
        print(f"  waiting: {len(pending)} not yet reporting, {len(failing)} reporting failure")
        if time.monotonic() >= deadline:
            return [
                f"{job}: {'never reported' if job in pending else 'probe_success=0'}"
                for job in jobs
                if job in pending or job in failing
            ]
        time.sleep(POLL_SECONDS)


def main():
    resources = state_resources()
    state = state_dialogues(resources)
    if not state:
        print("No smtp checks configured; step zero has nothing to prove.")
        return

    failures = compare_dialogues(state, stored_dialogues(resources))

    query_url, user, token = prometheus_credentials(resources)
    if not all((query_url, user, token)):
        failures.append("no Prometheus read credentials in state — cannot verify probe_success")
    elif not failures:
        print(f"== awaiting probe_success for {len(state)} smtp check(s)")
        failures += await_probes(query_url, user, token, sorted(state))

    if failures:
        sys.exit(
            "ERROR: step zero failed — nothing downstream is built until it passes:\n  "
            + "\n  ".join(failures)
            + "\n\nA check that never reports means the probes cannot egress port 25.\n"
            "A check reporting 0 means the conversation above did not complete;\n"
            "the probe's own log (Synthetic Monitoring in Grafana) shows how far it got."
        )

    print("Step zero passed: the dialogue survived storage and the probes report success.")


if __name__ == "__main__":
    main()
