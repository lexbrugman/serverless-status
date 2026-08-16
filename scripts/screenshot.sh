#!/usr/bin/env bash
# Regenerate the README screenshot from the rendered fixture, so the picture
# in the README is the page this repository produces today. The viewport is
# fixed: the image is a comparable artifact across changes, not a window
# somebody happened to size.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

set -a
# shellcheck source=/dev/null
source versions.env
set +a

FIXTURE="all-green"
VIEWPORT="920,1200"
SCALE=2
TARGET="docs/screenshot.png"

runtime="${CONTAINER_RUNTIME:-}"
if [[ -z "$runtime" ]]; then
  if command -v podman >/dev/null 2>&1; then
    runtime="podman"
  elif command -v docker >/dev/null 2>&1; then
    runtime="docker"
  else
    echo "ERROR: neither podman nor docker found (or set CONTAINER_RUNTIME)." >&2
    exit 1
  fi
fi

# Inside the repository, because the toolbox and the browser each see only
# this tree; out/ is the preview script's own gitignored directory.
work="out"
scripts/bootstrap-shell.sh scripts/preview.py --out "$work" >/dev/null
page="$work/${FIXTURE}/index.html"
if [[ ! -f "$page" ]]; then
  echo "ERROR: ${page} not rendered — preview.py no longer emits ${FIXTURE}." >&2
  exit 1
fi

# The image writes as its own user, so the namespace has to map to the one
# that owns the mount. --no-sandbox: the container is the sandbox, and
# Chromium's own wants privileges this run deliberately does not have.
user_args=(--user "$(id -u):$(id -g)")
if [[ "$runtime" == "podman" ]]; then
  user_args=(--userns=keep-id)
fi

"$runtime" run --rm "${user_args[@]}" -e HOME=/tmp -v "$ROOT/$work:/work:z" -w /work \
  "docker.io/zenika/alpine-chrome:${ALPINE_CHROME_VERSION}" \
  --no-sandbox --headless --disable-gpu --hide-scrollbars \
  --window-size="$VIEWPORT" --force-device-scale-factor="$SCALE" \
  --screenshot=/work/shot.png "file:///work/${FIXTURE}/index.html" >/dev/null 2>&1

cp "$work/shot.png" "$TARGET"
echo "Wrote ${TARGET} from the ${FIXTURE} fixture at ${VIEWPORT}@${SCALE}x."
