# The SMTP STARTTLS conversation, executed by the probe as expect -> send ->
# start_tls within each entry, entries strictly in order. The conversation
# ends at the upgrade: completing the TLS handshake is the STARTTLS
# validation, and a valid certificate for the host is asserted along with
# it.
#
# It cannot go further. Every entry reads a line — `expect` is required by
# the provider, and an empty pattern still consumes one — while after the
# upgrade the server says nothing until the client speaks. A post-upgrade
# EHLO would therefore block on a line that never arrives, and every smtp
# check would fail on its own timeout rather than on anything about the
# server.
#
# EVERY SPELLING BELOW IS LOAD-BEARING. The provider stores query_response
# as a set and sends it to the SM API sorted by an internal content hash,
# not in declaration order. These exact strings — including the casing of
# "Ehlo" and "StartTLS" (SMTP verbs are case-insensitive) and the fixed
# EHLO hostname — were chosen so that hash order equals dialogue order.
# Changing any character, or a provider release that changes the hashing,
# reorders the conversation on the wire into garbage.
# scripts/check-sm-payloads.py applies this module against a mock SM API
# and fails CI if the transmitted order ever diverges from the list below.
#
# The EHLO hostname is a constant, not configuration: a per-instance value
# would change the hashes and un-fix the order per instance. Probes never
# send MAIL, so the name only has to be syntactically valid; .invalid is
# reserved for exactly this.

output "entries" {
  description = "Ordered SMTP dialogue for a tcp check's query_response blocks."
  value = [
    { expect = "^220", send = "Ehlo status-check.invalid", start_tls = false },
    { expect = "^250", send = "StartTLS", start_tls = false },
    { expect = "^220", send = "", start_tls = true },
  ]
}
