"""bin/sync.sh rebuilds an instance from the template: logic replaced,
structure regenerated over the org set, data and state preserved."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REF = "2099.101.0"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def instance(tmp_path):
    target = tmp_path / "instance"
    subprocess.run(
        [str(ROOT / "scripts" / "new-instance.sh"), str(target)],
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    subprocess.run(["git", "init", "-q", str(target)], check=True)

    # A second org, filled data, a user-owned file, and template damage.
    stencil = (target / "org_example.tf").read_text()
    (target / "org_acme.tf").write_text(stencil.replace("example", "acme"))
    page = (target / "page.tf").read_text()
    (target / "page.tf").write_text(
        page.replace(
            "check_manifests    = [module.checks_example.check_manifest]",
            "check_manifests    = [module.checks_example.check_manifest, "
            "module.checks_acme.check_manifest]",
        )
    )
    state = (target / "state.tfbackend").read_text()
    (target / "state.tfbackend").write_text(
        state.replace("CHANGE-ME-state-bucket", "my-real-bucket")
    )
    (target / "RUNBOOK.md").write_text("mine\n")
    (target / "bootstrap" / "terraform.tfstate").write_text('{"fake": "state"}\n')
    wiring = target / "wiring" / "ci" / "main.tf"
    wiring.write_text(wiring.read_text() + "# CORRUPTED\n")
    (target / "wiring" / "stale-leftover.tf").write_text("stale\n")
    for command in (
        ["git", "add", "-A"],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
    ):
        subprocess.run(command, cwd=target, capture_output=True, check=True)
    return target


class TestSync:
    def test_rebuilds_logic_and_structure_preserving_data(self, instance):
        result = run(
            [
                str(instance / "bin" / "sync.sh"),
                "--source",
                str(ROOT / "template"),
                REF,
            ],
            cwd=instance,
        )
        assert result.returncode == 0, result.stderr

        wiring = (instance / "wiring" / "ci" / "main.tf").read_text()
        assert "CORRUPTED" not in wiring
        assert not (instance / "wiring" / "stale-leftover.tf").exists()

        acme = (instance / "org_acme.tf").read_text()
        assert acme.startswith("# Generated from org_example.tf by bin/sync.sh")
        assert 'module "checks_acme"' in acme
        assert "grafana.example_cloud" not in acme
        page = (instance / "page.tf").read_text()
        assert "module.checks_acme.check_manifest" in page
        assert "module.checks_example.check_manifest" in page
        assert f"?ref={REF}" in page and "?ref=master" not in page

        assert "my-real-bucket" in (instance / "state.tfbackend").read_text()
        assert (instance / "RUNBOOK.md").read_text() == "mine\n"
        assert '"fake"' in (instance / "bootstrap" / "terraform.tfstate").read_text()

    def test_fails_loudly_without_a_ref(self, instance):
        (instance / "page.tf").write_text("# no module sources\n")
        result = run(
            [str(instance / "bin" / "sync.sh"), "--source", str(ROOT / "template")],
            cwd=instance,
        )
        assert result.returncode == 1
        assert "no ref given and none found" in result.stderr
