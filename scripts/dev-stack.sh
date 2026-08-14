#!/usr/bin/env bash
# Local Lambda-runtime parity: DynamoDB Local, a canned Prometheus, and the
# real Lambda Python base image (which ships the Runtime Interface Emulator)
# with src/ mounted. Unit tests with moto cannot catch an import error, a
# bad handler signature, or a runtime incompatibility — this can.
#
# Everything auxiliary (table creation, the Prometheus mock) also runs inside
# the Lambda base image, so the host needs only a container runtime.
#
# Usage: dev-stack.sh [--down] [--state FIXTURE]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set -a
# shellcheck source=versions.env
source "$ROOT/versions.env"
set +a

runtime="${CONTAINER_RUNTIME:-}"
if [[ -z "$runtime" ]]; then
  if command -v podman >/dev/null; then
    runtime="podman"
  elif command -v docker >/dev/null; then
    runtime="docker"
  else
    echo "ERROR: neither podman nor docker found (or set CONTAINER_RUNTIME)." >&2
    exit 1
  fi
fi

network="serverless-status-dev"
lambda_image="public.ecr.aws/lambda/python:${LAMBDA_PYTHON_VERSION}"
ddb_image="docker.io/amazon/dynamodb-local:${DYNAMODB_LOCAL_VERSION}"
fixture_state="all-green"

down() {
  for name in sls-rie sls-prom sls-ddb; do
    "$runtime" rm -f "$name" >/dev/null 2>&1 || true
  done
  "$runtime" network rm "$network" >/dev/null 2>&1 || true
  echo "dev stack removed."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --down)
      down
      exit 0
      ;;
    --state)
      fixture_state="${2:?--state needs a fixture name}"
      shift 2
      ;;
    *)
      echo "usage: dev-stack.sh [--down] [--state FIXTURE]" >&2
      exit 1
      ;;
  esac
done

down >/dev/null

# The task directory mirrors the deployment zip: handler sources plus the
# baked-in manifest (the fixture one, locally).
task_dir="$ROOT/.devstack/task"
rm -rf "$task_dir"
mkdir -p "$task_dir"
cp "$ROOT"/modules/renderer/src/*.py "$task_dir/"
cp "$ROOT/tests/fixtures/manifest.json" "$task_dir/manifest.json"

"$runtime" network create "$network" >/dev/null

"$runtime" run -d --name sls-ddb --network "$network" --network-alias ddb \
  "$ddb_image" -jar DynamoDBLocal.jar -inMemory -sharedDb >/dev/null

"$runtime" run --rm --network "$network" \
  --entrypoint python3 \
  -v "$ROOT:/repo:ro" \
  -e DDB_ENDPOINT=http://ddb:8000 \
  -e TABLE_NAME=status-page \
  -e AWS_ACCESS_KEY_ID=local -e AWS_SECRET_ACCESS_KEY=local -e AWS_DEFAULT_REGION=eu-west-1 \
  "$lambda_image" /repo/tests/create_table.py

"$runtime" run -d --name sls-prom --network "$network" --network-alias prom \
  --entrypoint python3 \
  -v "$ROOT:/repo:ro" \
  "$lambda_image" /repo/tests/mock_prometheus.py --state "$fixture_state" --port 9090 >/dev/null

"$runtime" run -d --name sls-rie --network "$network" -p 9000:8080 \
  -v "$task_dir:/var/task:ro" \
  -e TABLE_NAME=status-page \
  -e DDB_ENDPOINT=http://ddb:8000 \
  -e PROM_ENDPOINT=http://prom:9090 \
  -e PAGE_VERSION=dev \
  -e AWS_ACCESS_KEY_ID=local -e AWS_SECRET_ACCESS_KEY=local -e AWS_DEFAULT_REGION=eu-west-1 \
  "$lambda_image" handler.render_handler >/dev/null

echo "dev stack up (fixture: $fixture_state). Invoke exactly as Lambda does:"
echo '  curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d "{}"'
echo "Tear down with: scripts/dev-stack.sh --down"
