# The local toolbox: every pinned tool, installed by the same bin/
# installers CI runs via setup-pinned-tools — one install mechanism, two
# consumers. Built on demand by scripts/bootstrap-shell.sh with a
# content-addressed tag, so nothing ever lands on the host.
#
# The base derives from LAMBDA_PYTHON_VERSION (versions.env): the test suite
# runs on the same interpreter line the Lambda runtime ships.
ARG PYTHON_VERSION
FROM docker.io/library/python:${PYTHON_VERSION}-slim

ARG OPENTOFU_VERSION
ARG TFLINT_VERSION
ARG SHELLCHECK_VERSION
ARG SHFMT_VERSION
ARG RUFF_VERSION
ARG ACTIONLINT_VERSION
ARG UV_VERSION
ARG PYTEST_VERSION
ARG PYTEST_COV_VERSION
ARG COVERAGE_VERSION
ARG BOTO3_VERSION
ARG MOTO_VERSION

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    unzip \
  && rm -rf /var/lib/apt/lists/*

COPY bin/ /tmp/bin/

# Every installer runs, so the toolbox carries every pinned tool by
# construction; each reads its <TOOL>_VERSION from the ARGs above. The
# digest-fallback installers call api.github.com unauthenticated here — a
# local one-off build, not a shared-runner IP.
RUN set -eux; \
  for installer in /tmp/bin/install-*.sh; do \
    "$installer" /usr/local/bin; \
  done; \
  rm -rf /tmp/bin
