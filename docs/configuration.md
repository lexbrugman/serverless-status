# Configuration

An instance states everything in `status.yaml`. The `.tf` files beside it
are generated from it and overwritten by every sync, and the one thing that
cannot live there is `state.tfbackend`, because a backend is configured
before any configuration is read.

## Checks

Adding a check is one entry under `checks`:

```yaml
checks:
  - grafana_org: example
    display: API
    group: Web
    type: https
    host: api.example.com
    path: /health
    latency_budget_ms: 800
```

A check is identified by its host, its protocol, and its port when that is
not the protocol's own — no name to invent. That identity becomes the
Prometheus `job` label, the DynamoDB partition key component, and the
resource address, so it is also the check's history: editing a path, a
display name, a frequency or a budget keeps it, and so does moving the
check to another account, while pointing it at a different host or port
starts a new one. Two checks alike in host, protocol and port need a `key`
on at least one; the plan names them when it happens.

`grafana_org` names the account (under `grafana_orgs`) whose probes run,
and whose budget pays for, the check. The instance routes each account's
slice to its own checks module and strips the routing attributes on the
way; the module's contract is account-agnostic. A check referencing an
unknown account fails the plan naming the offender.

| field | meaning |
|---|---|
| `display` | Optional row title; defaults to the host |
| `group` | Section on the page; groups order by their lowest member `order`, then name |
| `type` | The protocol, spelled out: `https`, `http`, `ping`, or `smtp` |
| `host` | Bare hostname — no scheme, port, or path; those are separate facts |
| `port` | Optional; type default; forbidden for `ping` |
| `path` | Optional; `https`/`http` only |
| `frequency_minutes` | Optional; how often the probe runs |
| `timeout_seconds` | Optional |
| `order` | Optional sort key within the group |
| `latency_budget_ms` | Optional; exceeded while up shows the amber "Slow" state |
| `alert` | Optional; `false` keeps a check off the notification path |
| `key` | Optional; only to separate two checks alike in host, protocol and port |

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

The checks module enforces each account's declared monthly execution
budget as a plan-time precondition — an over-budget check set fails the
plan naming the largest consumers — and reads the tenant's check quota from
the Synthetic Monitoring API, failing the plan when the configuration
exceeds what the account allows.

## Accounts

```yaml
grafana_orgs:
  example:
    stack_slug: examplecorp
    monthly_execution_budget: 90000
```

One entry per Grafana Cloud account, keyed by an identifier you choose.
Each account keeps its own billing and its own execution budget, and CI
generates a `grafana_org_<key>.tf` and its entries in `page.tf` from this
map. The budget is stated rather than read because no API publishes an
account's execution allowance.

## Alerting

```yaml
alerting:
  email_addresses: [ops@example.com]
  down_for_minutes: 5
```

Notification is Grafana's job, provisioned from here. Every check alerts
unless it says `alert: false`; an alert fires when `probe_success` has been
below 1 for `down_for_minutes`, and resolves when it comes back. Leave
`email_addresses` empty and no alerting is created at all.

The rules live in the stack, not in this stack's own AWS: an outage that
takes the renderer down still reaches a mailbox, because nothing of ours
sits between a failing probe and the message. Each account gets a folder, a
contact point, and one multi-dimensional rule that fans out per check.
Routing is attached to the rule itself, so the stack's notification policy
tree stays exactly as its owner arranged it.

A check that stops publishing alerts too. Silence means the check is no
longer being run, which is the failure nobody notices unaided.

## Site and page

```yaml
site:
  name: Example Corp
  title: Example Corp status                  # optional, defaults to "<name> status"
  description: Live availability of our services.   # optional
  timezone: Europe/Amsterdam                  # IANA; outage log and timestamps
  accent: "#16a34a"                           # optional
  logo_svg: |                                 # optional, inlined verbatim
    <svg xmlns="http://www.w3.org/2000/svg" …></svg>
  links:
    - label: example.com
      url: https://example.com

page:                     # all optional, defaults shown
  history_days: 90        # length of the uptime bars
  outage_log_days: 30     # reach of the derived incident list
  retention_days: 400     # DynamoDB TTL horizon
  refresh_seconds: 60     # meta-refresh and staleness threshold
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
