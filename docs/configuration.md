# Configuration

An instance states everything in `config.yaml`. The `.tf` files beside it
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
| `latency_budget_ms` | Optional; must be under `timeout_seconds` — a confirmed miss is the amber "Slow" state |
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

A key nothing declares is rejected too, at every level of the file
including inside lists and maps. This matters more than it sounds:
OpenTofu discards an attribute no type declares, silently, so
`latency_budget` where the field is `latency_budget_ms` would otherwise
give you a check with no budget and no complaint. Nothing maintains a list
of allowed keys — the check reads the type constraints out of the plan and
walks your file against them, so a field added upstream is known the moment
it exists.

The two allowances behave differently, because only one of them is
knowable in advance. Executions follow from the configuration — frequency
times probe locations — so they are projected and enforced. Metrics series
follow from what Synthetic Monitoring chooses to publish per check, which
is Grafana's to decide and is documented nowhere, so they are read from the
account and reported as `metrics_series_<account>`: series in use against
the ceiling the plan enforces. Note that the enforced ceiling sits above
the allowance a plan includes — 15k against 10k on the free tier — so the
number to watch is the smaller one. A pair of zeroes means the reading
failed rather than that there is room.

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
generates a `tofu/grafana_org_<key>.tf` and its entries in `tofu/page.tf`
from this map. The budget is stated rather than read because no API publishes an
account's execution allowance.

## Alerting

```yaml
alerting:
  email_addresses: [ops@example.com]
```

Notification is Grafana's job, provisioned from here. Every check pages you
when it fails unless it says `alert: false`, and an alert fires on the
literal query the page asks — the same PromQL string, compared between the
two layers by `scripts/check-cross-layer.py`, so the page and the pager
cannot come to tell different stories about the same check.

**Latency is shown, not paged.** A check past its budget goes amber, records
a degradation and moves its performance figure, and no rule watches it.
That is a decision rather than a gap: an outage should wake somebody, a
slow service is something a reader checking "is it me or you" needs to see
and an operator reads in the morning.

That definition is two numbers under `page`. `down_window_multiple` is how
many probe intervals a verdict is made over; `down_quorum` is the share of
the probe locations that must agree — that a check is up, and for one with
a latency budget, that it is inside it. One statement of how much evidence
is enough, asked of both questions. Counting executions
rather than minutes is what makes it a debounce: a wall-clock wait shorter
than the probe interval re-reads one sample, so it delays the alert without
ever requiring a second failure. Below 1, the quorum also absorbs a single
unhappy probe location, which is why Grafana recommends running alerting
checks from several.

Leave `email_addresses` empty and no alerting is created at all.

The rules live in the stack, not in this stack's own AWS: an outage that
takes the renderer down still reaches a mailbox, because nothing of ours
sits between a failing probe and the message. Each account gets a folder, a
contact point, and one multi-dimensional rule that fans out per check.
Routing is attached to the rule itself, so the stack's notification policy
tree stays exactly as its owner arranged it.

`alert: false` opts a check out of being paged about when it fails. It does
not opt it out of being watched: a check that stops reporting raises an
alert either way, because that is a failure of the monitoring rather than
of the thing monitored, and it is the one nobody notices unaided. It also
does not opt it out of the page — every check has its bars, its incidents
and its history whether or not a failure is worth a message.

A notification names the check and its target rather than the job label
Grafana knows it by, says whether it is the failure or the recovery, and
links to the page. It states no duration on purpose: an incident is stamped
at the sample it began, and Grafana can only know when its own window
filled, so any figure it quoted would disagree with the log it points at.

Two more rules cover the failures a down-check rule cannot see. The
renderer publishes the moment of its last successful run, and an alert
fires when that goes stale — a page that stops rendering serves its last
render perfectly, so nothing else would notice. It also publishes, per
check, whether that run heard from it at all; a check that stops reporting
raises its own alert. Absence carries no labels, so Grafana cannot ask
which check went missing: only the renderer holds the configured set, and
so only the renderer can say what is not there.

## Site and page

```yaml
site:
  name: Example Corp
  title: Example Corp status                  # optional, defaults to "<name> status"
  description: Live availability of our services.   # optional
  timezone: Europe/Amsterdam                  # IANA; every time and day on the page
  accent: "#16a34a"                           # optional
  logo_svg: |                                 # optional, inlined verbatim
    <svg xmlns="http://www.w3.org/2000/svg" …></svg>
  links:
    - label: example.com
      url: https://example.com

page:                     # all optional, defaults shown
  history_days: 90        # length of the uptime bars, and the longest window
  outage_log_days: 30     # reach of the derived incident list
  retention_days: 400     # DynamoDB TTL horizon
  refresh_seconds: 60     # meta-refresh and staleness threshold
  down_window_multiple: 3 # a verdict is made over this many probe intervals
  down_quorum: 0.5        # the share of those executions that must succeed
```

A page cannot promise more history than the table keeps:
`retention_days >= history_days` and `outage_log_days <= retention_days`
are enforced.

`timezone` is the page's single frame of reference. Timestamps are stored
UTC and rendered in it, and the uptime bars split days at its midnight
rather than UTC's — so past midnight a new bar appears when the clock on
the page says it should. Days already recorded keep the boundary they were
written with, which is a couple of hours at one edge and invisible against
a daily ratio. An unknown zone name stops the renderer rather than quietly
serving every time a few hours wrong.

**Deliberately not knobs:** light/dark (always both), `status.json` and
`badge.svg` (always shipped), fonts (system stack), layout, language, and
the semantic up/amber/down colours. A status page whose green is
configurable is a status page nobody can read at a glance.

## What the page's numbers mean

One figure is the answer, and it carries its own name. Everything else is
behind the disclosure under it, because a reader arrives asking whether the
thing works and cannot tell which of nine percentages was the one to read.

**Availability** is the headline: the share of observed time with no
confirmed outage against it, in wall-clock seconds, measured against the
incident log — which holds both kinds of period, so an amber day is always
nameable in the list below it. It is also offered over 24 hours, 7 and 30 days, since a
ninety-day figure cannot say whether something is flaky right now.

**Performance** is the same measurement against the degradation log: the
share of observed time no confirmed degradation covers, for the checks that
declare a `latency_budget_ms`. Same records, same arithmetic, different
subject.

**Probe success** is the share of individual probe executions that
succeeded — executions rather than time, pooled across every probe
location. It is the raw signal underneath the debounce and it is a
diagnostic, not a verdict: it drops whenever a single location flaps, which
is precisely what the verdicts filter out. It is disclosed, never shown
beside the answer.

### Anything shown as a degradation filters probe locations

No state the page displays — red, amber, the pill, the banner — can be
raised by a dissenting minority of probe locations. Down and slow are the
same construction: the share of locations agreeing at each instant, judged
against `down_quorum` over `down_window_multiple` intervals, then recorded
as a period with the moment it started. A mean cannot filter a minority and
only a quorum can, which is why nothing on the page averages locations to
decide a state. With a single probe location there is no minority to
filter, and the same construction reduces to the time debounce alone.

A latency budget only means anything between itself and the probe's own
timeout. An execution running past `timeout_seconds` reports failure, so a
check whose budget reaches the timeout can read up or down but never slow;
the plan rejects that rather than serving a state nothing can enter.

None of these count time nobody observed. A day without samples is a hole
in all of them — grey in the bar, absent from every ratio — and the page
says how many of the window's days it holds whenever that is not all of
them. A window the table has five days of is not a ninety-day record, and
silence is the one failure a success ratio would otherwise reward.

## Machine outputs

`status.json` carries its own `schema_version` — a public contract with
consumers, independent of the internal module seam. `badge.svg` is a
shields-style badge colored by the overall state. Both live next to
`index.html` and obey the zero-external-dependency rule.

Its `incidents` array is the whole confirmed log over `history_days`, not
the shorter list the page prints under **Recent incidents** — a machine
output that held less than the page describing it would leave a consumer
unable to reproduce what a reader can see. Both spans are stated, so
either view is derivable:

| Field | Covers |
| --- | --- |
| `history_days` | The record: every uptime bar, every availability figure, and `incidents` itself. |
| `recent_incident_days` | Where the page draws the line under **Recent incidents**. Filter `incidents` by it to reproduce that section. |

Each entry carries its check's `key`, so grouping by it reproduces the
per-check list a row discloses.
