"""bin/sync.sh rebuilds an instance from the template: logic replaced,
structure regenerated over the org set, data and state preserved."""

import shutil
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

    # A second account in the data file, filled data, a user-owned file, a
    # generated account file for a key the config no longer has, and
    # template damage.
    config = target / "config.yaml"
    config.write_text(
        config.read_text().replace(
            "grafana_orgs:\n",
            "grafana_orgs:\n  acme:\n    stack_slug: acmecorp\n"
            "    monthly_execution_budget: 90000\n",
        )
    )
    stencil = (target / "tofu" / "grafana_org_example.tf").read_text()
    (target / "tofu" / "grafana_org_zombie.tf").write_text(stencil.replace("example", "zombie"))
    state = (target / "state.tfbackend").read_text()
    (target / "state.tfbackend").write_text(
        state.replace("CHANGE-ME-state-bucket", "my-real-bucket")
    )
    (target / "RUNBOOK.md").write_text("mine\n")
    (target / "tofu" / "bootstrap" / "terraform.tfstate").write_text('{"fake": "state"}\n')
    wiring = target / "tofu" / "wiring" / "ci" / "main.tf"
    wiring.write_text(wiring.read_text() + "# CORRUPTED\n")
    (target / "tofu" / "wiring" / "stale-leftover.tf").write_text("stale\n")
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

        wiring = (instance / "tofu" / "wiring" / "ci" / "main.tf").read_text()
        assert "CORRUPTED" not in wiring
        assert not (instance / "tofu" / "wiring" / "stale-leftover.tf").exists()
        assert not (instance / "tofu" / "grafana_org_zombie.tf").exists()

        acme = (instance / "tofu" / "grafana_org_acme.tf").read_text()
        assert acme.startswith("# Generated from grafana_org_example.tf by bin/sync.sh")
        assert 'module "checks_acme"' in acme
        assert "grafana.example_cloud" not in acme
        page = (instance / "tofu" / "page.tf").read_text()
        assert "module.checks_acme.check_manifest" in page
        assert "module.checks_example.check_manifest" in page
        assert f"?ref={SYNC_REF}" in page
        assert FAKE_TAG not in page and "?ref=master" not in page

        assert "my-real-bucket" in (instance / "state.tfbackend").read_text()
        assert (instance / "RUNBOOK.md").read_text() == "mine\n"
        assert '"fake"' in (instance / "tofu" / "bootstrap" / "terraform.tfstate").read_text()

    def test_a_release_that_moves_a_file_leaves_no_orphan(self, repo, instance, tmp_path):
        """The sync an instance runs comes from the release it is leaving, so
        the record of what was generated — not this release's own idea of
        what it owns — decides what goes."""
        first = run(
            [str(instance / "bin" / "sync.sh"), "--source", str(repo / "template"), SYNC_REF],
            cwd=instance,
        )
        assert first.returncode == 0, first.stderr
        assert (instance / ".sync-manifest").exists()

        # A later release that renames a script.
        moved = tmp_path / "moved-template"
        shutil.copytree(repo / "template", moved)
        (moved / "bin" / "ci-plan.sh").rename(moved / "bin" / "ci-planning.sh")

        second = run(
            [str(instance / "bin" / "sync.sh"), "--source", str(moved), SYNC_REF], cwd=instance
        )
        assert second.returncode == 0, second.stderr
        assert (instance / "bin" / "ci-planning.sh").exists()
        assert not (instance / "bin" / "ci-plan.sh").exists(), "the old path must not linger"

    def test_state_survives_a_release_that_moves_the_roots(self, repo, instance, tmp_path):
        """Stranding a state file is untidy; deleting one destroys the only
        record of what exists."""
        moved = tmp_path / "moved-template"
        shutil.copytree(repo / "template", moved)
        (moved / "tofu").rename(moved / "stack")

        result = run(
            [str(instance / "bin" / "sync.sh"), "--source", str(moved), SYNC_REF], cwd=instance
        )
        assert result.returncode == 0, result.stderr
        assert (instance / "stack").is_dir(), "the release's own layout lands"
        assert '"fake"' in (instance / "tofu" / "bootstrap" / "terraform.tfstate").read_text()

    def test_fails_loudly_without_a_ref(self, repo, instance):
        (instance / "tofu" / "page.tf").write_text("# no module sources\n")
        result = run(
            [str(instance / "bin" / "sync.sh"), "--source", str(repo / "template")],
            cwd=instance,
        )
        assert result.returncode == 1
        assert "no ref given and no module pin" in result.stderr

    def test_fails_loudly_without_accounts(self, repo, instance):
        config = instance / "config.yaml"
        content = config.read_text()
        start = content.index("grafana_orgs:")
        end = content.index("\nchecks:", start)
        config.write_text(content[:start] + "grafana_orgs: {}" + content[end:])
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
        assert "no accounts under grafana_orgs" in result.stderr
