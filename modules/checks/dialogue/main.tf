# The SMTP STARTTLS conversation, executed by the probe as expect -> send ->
# start_tls within each entry, entries strictly in order. The TLS handshake
# completing is the STARTTLS validation; the post-upgrade EHLO/QUIT proves
# the secured channel still speaks SMTP.
#
# EVERY SPELLING BELOW IS LOAD-BEARING. The provider stores query_response
# as a set and sends it to the SM API sorted by an internal content hash,
# not in declaration order. These exact strings — including the casing of
# "Ehlo", "StartTLS", and "quit" (SMTP verbs are case-insensitive) and the
# fixed EHLO hostname — were chosen so that hash order equals dialogue
# order. Changing any character, or a provider release that changes the
# hashing, reorders the conversation on the wire into garbage.
# scripts/check-smtp-dialogue.py applies this module against a mock SM API
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
    { expect = "", send = "EHLO status-check.invalid", start_tls = false },
    { expect = "^250", send = "quit", start_tls = false },
  ]
}
