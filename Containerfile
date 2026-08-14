# The local toolbox: every pinned tool, installed by the same bin/
# installers CI runs via setup-pinned-tools — one install mechanism, two
# consumers. Built on demand by scripts/bootstrap-shell.sh with a
# content-addressed tag, so nothing ever lands on the host.
#
# The base derives from LAMBDA_PYTHON_VERSION (versions.env): the test suite
# runs on the same interpreter line the Lambda runtime ships.
ARG PYTHON_VERSION
FROM docker.io/library/python:${PYTHON_VERSION}-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    unzip \
  && rm -rf /var/lib/apt/lists/*

COPY bin/ /tmp/bin/
COPY versions.env /tmp/versions.env

# Every installer runs with every version exported, so the toolbox carries
# every pinned tool by construction and a new tool is one installer plus a
# versions.env entry — no list here to forget. The tag already hashes
# versions.env, so sourcing it cannot go stale. The digest-fallback
# installers call api.github.com unauthenticated here — a local one-off
# build, not a shared-runner IP.
RUN set -eux; \
  set -a; . /tmp/versions.env; set +a; \
  for installer in /tmp/bin/install-*.sh; do \
    "$installer" /usr/local/bin; \
  done; \
  rm -rf /tmp/bin /tmp/versions.env
