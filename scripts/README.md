# Scripts

`bootstrap-shell.sh` is the local entry point: it runs any command in the
toolbox container (every pinned tool, nothing on the host), building the
image on demand with a tag hashed from its inputs.

The gate pair, run by CI and locally through the toolbox:

- `lint.sh` — shellcheck, shfmt, ruff (lint + format), actionlint,
  `tofu fmt`, the identity sweep, the template-ref guard, and the
  cross-layer mirrors.
- `test.sh` — pytest (100% line+branch on the renderer source) and
  `tofu test` in each module.

The specialised checks, each its own CI job:

- `preview.py` — render every fixture state and validate the output; with
  `--serve`, browse them (`BOOTSTRAP_PUBLISH=8000` through the toolbox).
- `check-template.sh` — validate the template as a root, with module
  sources rewritten to local paths.
- `check-smtp-dialogue.py` — apply the SMTP dialogue against a mock SM API
  and assert the provider transmits it in order.
- `check-integration.py` — invoke the dev stack's Lambda and validate the
  response; the runtime-parity gate.
- `check-cross-layer.py` — assert the mirrored Lambda Python version agrees
  everywhere (called by lint.sh).
- `tofu-checks.sh` — init/validate/tflint one module directory.

Host-side by necessity (they drive the container runtime themselves):

- `dev-stack.sh` — DynamoDB Local + canned Prometheus + the real Lambda
  runtime image, for `check-integration.py` and manual poking.

Release and bootstrap:

- `next-version.sh` — the next CalVer tag for today.
- `release.sh` — tag HEAD and publish the release (CI only, master).
- `new-instance.sh` — copy the template into a private instance root,
  stamping the module refs to the latest release.
