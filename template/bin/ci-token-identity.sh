#!/usr/bin/env bash
# Prints the OIDC token's claims. The hand-made trust must match these
# exactly; printing them turns a refused assume from archaeology into a
# diff.
set -euo pipefail

: "${ACTIONS_ID_TOKEN_REQUEST_URL:?}" "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:?}"

curl -sH "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com" |
  jq -r '.value' | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null |
  jq '{iss, aud, sub}'
