# Configuration

## Checks

One map drives every check resource; adding a check is one entry in
`checks.auto.tfvars`. The map key becomes the Prometheus `job` label, the
DynamoDB partition key component, and the resource address, so a rename is a
deliberate destroy-and-recreate. Keys match `^[a-z0-9][a-z0-9-]*$`.

In the instance, each entry also carries `org` — the Grafana account
(`orgs.auto.tfvars`) whose probes run, and whose budget pays for, the
check. The instance routes each org's slice to its own checks module and
strips the attribute on the way; the module's contract is org-agnostic. A
check referencing an unknown org fails the plan naming the offender.

```hcl
checks = {
  api = {
    display           = "API"
    group             = "Web"
    type              = "https"
    host              = "api.example.com"
    path              = "/health"
    latency_budget_ms = 800
  }
}
```

| field | meaning |
|---|---|
| `display` | Row title on the page |
| `group` | Section on the page; groups order by their lowest member `order`, then name |
| `type` | The protocol, spelled out: `https`, `http`, `ping`, or `smtp` |
| `host` | Bare hostname — no scheme, port, or path; those are separate facts |
| `port` | Optional; type default; forbidden for `ping` |
| `path` | Optional; `https`/`http` only |
| `frequency_minutes` | Optional; how often the probe runs |
| `timeout_seconds` | Optional |
| `order` | Optional sort key within the group |
| `latency_budget_ms` | Optional; exceeded while up shows the amber "Slow" state |

Defaults by type:

| type | port | frequency | timeout |
|---|---|---|---|
| `https` | 443 | 5 min | 5 s |
| `http` | 80 | 5 min | 5 s |
| `smtp` | 25 | 5 min | 10 s |
| `ping` | — | 10 min | 3 s |

A scheme inside the target would be redundant with `type` at best and
contradictory at worst; string-parsing a URL back apart is not validation.
Every invalid combination is rejected at plan time with a message that
states the fix.

The checks module also enforces a monthly execution budget against the
Grafana Cloud free tier as a plan-time precondition; an over-budget check
set fails the plan naming the largest consumers.

## Site and page

```hcl
site = {
  name        = "Example Corp"
  title       = "Example Corp status"                  # optional, defaults to "<name> status"
  description = "Live availability of our services."   # optional
  timezone    = "Europe/Amsterdam"                     # IANA; outage log and timestamps
  accent      = "#16a34a"                              # optional
  logo_svg    = file("logo.svg")                       # optional, inlined
  links       = [{ label = "example.com", url = "https://example.com" }]
}

page = {                  # all optional, defaults shown
  history_days    = 90    # length of the uptime bars
  outage_log_days = 30    # reach of the derived incident list
  retention_days  = 400   # DynamoDB TTL horizon
  refresh_seconds = 60    # meta-refresh and staleness threshold
}
```

A page cannot promise more history than the table keeps:
`retention_days >= history_days` and `outage_log_days <= retention_days`
are enforced.

**Deliberately not knobs:** light/dark (always both), `status.json` and
`badge.svg` (always shipped), fonts (system stack), layout, language, and
the semantic up/amber/down colours. A status page whose green is
configurable is a status page nobody can read at a glance.

## Machine outputs

`status.json` carries its own `schema_version` — a public contract with
consumers, independent of the internal module seam. `badge.svg` is a
shields-style badge colored by the overall state. Both live next to
`index.html` and obey the zero-external-dependency rule.
