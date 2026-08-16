#!/usr/bin/env python3
"""Resolve this repository as AWS will see it, from the OIDC token itself.

The trust policy matches the token's sub claim, and only the issuer knows
how that claim is spelled: plain owner/name, or owner@id/name@id where the
organisation issues immutable subject claims. Reading it from the token
makes the written policy and the identity presenting itself the same
string by construction — a configured spelling can disagree, and a trust
that disagrees refuses every assume.
"""

import base64
import json
import os
import urllib.request

AUDIENCE = "sts.amazonaws.com"


def main():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request = urllib.request.Request(
        f"{url}&audience={AUDIENCE}",
        headers={"Authorization": f"bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)["value"]

    # JWT segments are unpadded base64url; the padding decides whether a
    # decoder accepts them at all.
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    subject = json.loads(base64.urlsafe_b64decode(payload))["sub"]

    # sub is repo:<repository>:<context>, where <context> is the branch,
    # pull request, or environment the run is bound to.
    repository = subject.split(":")[1]

    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
        env.write(f"TF_VAR_github_repository={repository}\n")
    print(f"repository, as the token's sub claim spells it: {repository}")


if __name__ == "__main__":
    main()
