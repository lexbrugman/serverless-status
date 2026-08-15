"""new-instance.sh stamping, verified in a disposable clone with a fake
release tag — the real repo's tag state must not influence the suite."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TAG = "2099.101.0"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    clone = tmp_path_factory.mktemp("clone") / "repo"
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for path in listed:
        source = ROOT / path
        target = clone / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        ["git", "tag", TAG],
    ):
        subprocess.run(command, cwd=clone, capture_output=True, check=True)
    return clone


class TestNewInstance:
    def test_stamps_every_module_ref(self, repo, tmp_path):
        target = tmp_path / "instance"
        result = run([str(repo / "scripts" / "new-instance.sh"), str(target)], cwd=repo)
        assert result.returncode == 0, result.stderr
        stamped = (target / "main.tf").read_text()
        assert "?ref=master" not in stamped
        assert stamped.count(f"?ref={TAG}") == 2
        assert (target / "checks.auto.tfvars").exists()
        assert (target / ".github" / "workflows" / "ci.yml").exists()
        assert (target / "bootstrap" / "main.tf").exists()

    def test_refuses_a_non_empty_target(self, repo, tmp_path):
        target = tmp_path / "occupied"
        target.mkdir()
        (target / "something").write_text("x")
        result = run([str(repo / "scripts" / "new-instance.sh"), str(target)], cwd=repo)
        assert result.returncode == 1
        assert "exists and is not empty" in result.stderr

    def test_fails_loudly_without_a_release(self, repo, tmp_path):
        untagged = tmp_path / "untagged"
        shutil.copytree(repo, untagged)
        subprocess.run(["git", "tag", "-d", TAG], cwd=untagged, capture_output=True, check=True)
        result = run(
            [str(untagged / "scripts" / "new-instance.sh"), str(tmp_path / "out")], cwd=untagged
        )
        assert result.returncode == 1
        assert "no release tag found" in result.stderr
