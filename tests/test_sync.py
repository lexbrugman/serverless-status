"""bin/sync.sh rebuilds an instance from the template: logic replaced,
structure regenerated over the org set, data and state preserved."""

import subprocess

import pytest
from conftest import FAKE_TAG

SYNC_REF = "2099.102.0"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def instance(repo, tmp_path):
    target = tmp_path / "instance"
    subprocess.run(
        [str(repo / "scripts" / "new-instance.sh"), str(target)],
        capture_output=True,
        check=True,
        cwd=repo,
    )
    subprocess.run(["git", "init", "-q", str(target)], check=True)

    # A second org in the data file, filled data, a user-owned file, a
    # hand-made org file for a key the map no longer has, and template
    # damage.
    tfvars = target / "instance.auto.tfvars"
    tfvars.write_text(
        tfvars.read_text().replace(
            "orgs = {",
            'orgs = {\n  acme = {\n    stack_slug               = "acmecorp"'
            "\n    monthly_execution_budget = 90000\n  }",
        )
    )
    stencil = (target / "org_example.tf").read_text()
    (target / "org_zombie.tf").write_text(stencil.replace("example", "zombie"))
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
    def test_rebuilds_logic_and_structure_preserving_data(self, repo, instance):
        result = run(
            [
                str(instance / "bin" / "sync.sh"),
                "--source",
                str(repo / "template"),
                SYNC_REF,
            ],
            cwd=instance,
        )
        assert result.returncode == 0, result.stderr

        wiring = (instance / "wiring" / "ci" / "main.tf").read_text()
        assert "CORRUPTED" not in wiring
        assert not (instance / "wiring" / "stale-leftover.tf").exists()
        assert not (instance / "org_zombie.tf").exists()

        acme = (instance / "org_acme.tf").read_text()
        assert acme.startswith("# Generated from org_example.tf by bin/sync.sh")
        assert 'module "checks_acme"' in acme
        assert "grafana.example_cloud" not in acme
        page = (instance / "page.tf").read_text()
        assert "module.checks_acme.check_manifest" in page
        assert "module.checks_example.check_manifest" in page
        assert f"?ref={SYNC_REF}" in page
        assert FAKE_TAG not in page and "?ref=master" not in page

        assert "my-real-bucket" in (instance / "state.tfbackend").read_text()
        assert (instance / "RUNBOOK.md").read_text() == "mine\n"
        assert '"fake"' in (instance / "bootstrap" / "terraform.tfstate").read_text()

    def test_fails_loudly_without_a_ref(self, repo, instance):
        (instance / "page.tf").write_text("# no module sources\n")
        result = run(
            [str(instance / "bin" / "sync.sh"), "--source", str(repo / "template")],
            cwd=instance,
        )
        assert result.returncode == 1
        assert "no ref given and none found" in result.stderr

    def test_fails_loudly_without_org_keys(self, repo, instance):
        tfvars = instance / "instance.auto.tfvars"
        content = tfvars.read_text()
        start = content.index("orgs = {")
        end = content.index("\n}", start)
        tfvars.write_text(content[:start] + "orgs = {" + content[end:])
        result = run(
            [
                str(instance / "bin" / "sync.sh"),
                "--source",
                str(repo / "template"),
                SYNC_REF,
            ],
            cwd=instance,
        )
        assert result.returncode == 1
        assert "no org keys found" in result.stderr
