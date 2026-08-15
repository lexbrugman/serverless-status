# The only file touched day-to-day: every monitored endpoint, keyed by a
# stable identifier. `org` names the account (the orgs map in
# instance.auto.tfvars) whose probes run — and whose budget pays for — the
# check. A key rename is a deliberate destroy-and-recreate of that check's
# history. Adding check #10 is one entry here.
checks = {
  website = {
    org     = "example"
    display = "Website"
    group   = "Web"
    type    = "https"
    host    = "www.example.com"
    order   = 10
  }

  api = {
    org               = "example"
    display           = "API"
    group             = "Web"
    type              = "https"
    host              = "api.example.com"
    path              = "/health"
    latency_budget_ms = 800
    order             = 20
  }

  mail-inbound = {
    org     = "example"
    display = "Inbound mail (SMTP + STARTTLS)"
    group   = "Mail"
    type    = "smtp"
    host    = "mx1.example.com"
    order   = 30
  }

  office-uplink = {
    org     = "example"
    display = "Office connectivity"
    group   = "Network"
    type    = "ping"
    host    = "gw.example.com"
    order   = 40
  }
}
