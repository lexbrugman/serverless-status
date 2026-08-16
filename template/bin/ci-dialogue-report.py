#!/usr/bin/env python3
"""Print every smtp check's TCP dialogue two ways — the provider's
read-back in state, and what the SM API actually stores, decoded. The
stored form is the one surface no plan, state, or CI mock can show
(scripts/check-sm-payloads.py in the public repository asserts the
provider's transmission; this reports the backend's side), and it is what
the probes execute."""

import base64
import json
import subprocess
import urllib.request


def walk(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from walk(child)


def decoded(value):
    return base64.b64decode(value or "").decode(errors="replace")


def main():
    shown = subprocess.run(["tofu", "show", "-json"], capture_output=True, text=True, check=True)
    state = json.loads(shown.stdout)
    resources = list(walk(state.get("values", {}).get("root_module", {})))

    for resource in resources:
        if resource["type"] != "grafana_synthetic_monitoring_check":
            continue
        if ".smtp[" not in resource["address"]:
            continue
        print(f"== state read-back: {resource['address']}")
        tcp = resource["values"]["settings"][0]["tcp"][0]
        for i, entry in enumerate(tcp.get("query_response") or []):
            print(
                f"  {i}: expect={entry.get('expect')!r}"
                f" send={entry.get('send')!r}"
                f" start_tls={entry.get('start_tls')}"
            )

    for resource in resources:
        if resource["type"] != "grafana_synthetic_monitoring_installation":
            continue
        url = resource["values"]["stack_sm_api_url"].rstrip("/")
        token = resource["values"]["sm_access_token"]
        request = urllib.request.Request(
            f"{url}/api/v1/check/list", headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(request) as response:
            checks = json.load(response)
        for check in checks:
            tcp = check.get("settings", {}).get("tcp")
            if not tcp:
                continue
            print(f"== SM API stored: {check['job']} (via {resource['address']})")
            for i, entry in enumerate(tcp.get("queryResponse") or []):
                print(
                    f"  {i}: expect={decoded(entry.get('expect'))!r}"
                    f" send={decoded(entry.get('send'))!r}"
                    f" startTLS={entry.get('startTLS', False)}"
                )


if __name__ == "__main__":
    main()
