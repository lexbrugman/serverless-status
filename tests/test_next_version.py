"""next-version.sh arithmetic, in a disposable repo so real tags cannot
influence the suite."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def today_prefix() -> str:
    now = datetime.now(UTC)
    return f"{now.year}.{now.month}{now.day:02d}"


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "x").write_text("x")
    for command in (
        ["git", "add", "x"],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
    ):
        subprocess.run(command, cwd=tmp_path, capture_output=True, check=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "next-version.sh").write_bytes(
        (ROOT / "scripts" / "next-version.sh").read_bytes()
    )
    (tmp_path / "scripts" / "next-version.sh").chmod(0o755)
    return tmp_path


def next_version(repo: Path) -> str:
    return subprocess.run(
        [str(repo / "scripts" / "next-version.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


class TestNextVersion:
    def test_first_release_of_the_day_is_patch_zero(self, repo):
        assert next_version(repo) == f"{today_prefix()}.0"

    def test_same_day_releases_increment(self, repo):
        subprocess.run(["git", "tag", f"{today_prefix()}.0"], cwd=repo, check=True)
        assert next_version(repo) == f"{today_prefix()}.1"

    def test_patch_sorts_numerically_not_lexically(self, repo):
        for patch in range(11):
            subprocess.run(["git", "tag", f"{today_prefix()}.{patch}"], cwd=repo, check=True)
        assert next_version(repo) == f"{today_prefix()}.11"

    def test_other_days_do_not_interfere(self, repo):
        subprocess.run(["git", "tag", "2001.101.5"], cwd=repo, check=True)
        assert next_version(repo) == f"{today_prefix()}.0"
