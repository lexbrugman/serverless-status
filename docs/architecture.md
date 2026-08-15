# Architecture

A serverless status page on a custom domain, free-tier all the way down:
Grafana Cloud runs the probes, AWS renders and serves the page.

```
Grafana Cloud (free)                AWS (always-free)
┌──────────────────────┐            ┌────────────────────────┐
│ Synthetic Monitoring │            │ EventBridge Scheduler  │
│  https · ping · smtp │            │        │ 1/min         │
│         │            │  metrics   │        ▼               │
│         ▼            │  read      │     Lambda ──► DynamoDB│
│   Prometheus  ───────┼───────────►│        │       history │
└──────────────────────┘            │        ▼               │
                                    │       S3 ──► CloudFront│
                                    │              + ACM     │
                                    └────────────────────────┘
                                              │
                                       status.example.com
```

## Why the split

**Probing is Grafana's.** AWS cannot do it at this price or capability:
CloudWatch Synthetics bills per canary run, Route 53 health checks have no
ICMP, and Lambda-as-prober has no raw sockets (no ping) and blocked outbound
port 25 (no SMTP).

**Rendering is AWS's.** Lambda, DynamoDB, and CloudFront are always-free
with no expiry, unlike the 12-month tier.

**OpenTofu, not CDK.** The stack spans two control planes, and one apply
hands a credential from the first to the second (the Synthetic Monitoring
installation output configures the `grafana.sm` provider; the metrics-read
token flows into SSM). CloudFormation speaks only AWS. Two OpenTofu-specific
properties matter here: client-side state encryption answers the token in
state, and S3 native locking removes the lock table.

## The modules

`modules/checks` (Grafana leg) owns the probes, the execution-budget
precondition, the metrics-read access policy, and emits `page_manifest` —
the seam. `modules/renderer` (AWS leg) asserts the manifest's
`schema_version` at plan time and owns everything that renders and serves.

Modules create only what they own the entire lifecycle of and read
everything that predates them: the Grafana stack and the Route 53 zone are
looked up, never created. The state bucket is OpenTofu-managed by a
separate bootstrap root whose own state lives in the instance repository,
so the main stack can never delete its own state store. Destroying this
stack can never take down the zone. Providers are configured in roots only; `moved` blocks
are mandatory on every refactor because master is release.

## The SMTP dialogue

The mail conversation is first-class data, not a port knock: greeting, EHLO,
STARTTLS, TLS upgrade, EHLO again on the secured channel, QUIT. A server
that accepts connections but fails STARTTLS negotiation shows as down.

The provider transmits `query_response` blocks in content-hash order, not
declaration order. The exact spellings in `modules/checks/dialogue/` are
chosen so both orders coincide, and `scripts/check-smtp-dialogue.py` applies
the dialogue against a local mock of the SM API in CI to prove the wire
order every run — a provider upgrade that would scramble the conversation
turns red before it ships.

## Data model

One DynamoDB table, three item kinds:

- `SITE / LATEST` — the last real observation per check; overwritten by
  every non-degraded run. It is both the render fallback and the previous
  state for transition detection.
- `CHECK#<key> / DAY#<date>` — daily rollups, folded with an atomic `ADD`
  so retries cannot double-count. The 24-hour sparkline comes from
  Prometheus at render time; DynamoDB holds only distilled daily numbers.
- `CHECK#<key> / OUTAGE#<started_at>` — written on transition, closed on
  recovery. The data *is* the incident log: daily ratios cannot show a
  twenty-minute outage.

TTL on `expires_at` reclaims rollups and outages in the background. Raw
per-probe metrics live in Grafana Cloud's Prometheus, managed by them.

## The render cycle

Every minute the Scheduler invokes the Lambda, which queries Prometheus for
current state and the 24-hour latency series, detects transitions, folds
today's rollup, reads the history window, assembles one state dict, renders
`index.html` + `status.json` + `badge.svg`, and puts them to S3 with
`max-age=30` — the edge refreshes itself; no invalidation is ever issued.

**Degradation is honest.** If Prometheus is unreachable the page renders
from the cached snapshot plus stored rollups, says so visibly, and writes no
history — a Grafana outage never corrupts history with false downtime, and
the snapshot keeps the timestamp of the last real observation. Never a 500,
never stale green presented as current. The page also watches itself: an
inline script compares the embedded render time against the client clock and
surfaces a staleness banner when the renderer has died.

## Zero external page dependencies

Inline CSS, inline SVG, system fonts; no CDN, no font host, no analytics. A
status page that needs a third party to render is a status page that goes
down with the thing it reports on. The render tests reject any external
reference outside the configured `site.links`.
