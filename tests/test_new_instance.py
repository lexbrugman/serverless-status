"""new-instance.sh stamping, verified in the disposable tagged clone."""

import re
import shutil
import subprocess

from conftest import FAKE_TAG as TAG


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


class TestNewInstance:
    def test_stamps_every_module_ref(self, repo, tmp_path):
        target = tmp_path / "instance"
        result = run([str(repo / "scripts" / "new-instance.sh"), str(target)], cwd=repo)
        assert result.returncode == 0, result.stderr
        stamped = "".join(f.read_text() for f in target.rglob("*.tf"))
        refs = set(re.findall(r"//modules/[a-z]+\?ref=([^\"]+)", stamped))
        assert refs == {TAG}, f"every module source pins the release, got {refs}"
        assert (target / "config.yaml").exists()
        assert (target / ".github" / "workflows" / "ci.yml").exists()
        assert (target / "tofu" / "bootstrap" / "main.tf").exists()

    def test_accepts_a_clone_of_an_empty_repository(self, repo, tmp_path):
        target = tmp_path / "cloned-empty"
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        result = run([str(repo / "scripts" / "new-instance.sh"), str(target)], cwd=repo)
        assert result.returncode == 0, result.stderr
        assert (target / "tofu" / "main.tf").exists()

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
