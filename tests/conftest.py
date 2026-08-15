import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "modules" / "renderer" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

# handler reads these at import; the suite must never touch a real account.
os.environ.setdefault("MANIFEST_PATH", str(ROOT / "tests" / "fixtures" / "manifest.json"))
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")

# The fake release tag the disposable clone carries — the real repo's tag
# state must not influence the suite.
FAKE_TAG = "2099.101.0"


@pytest.fixture(scope="session")
def repo(tmp_path_factory):
    """A disposable clone of the working tree, committed and tagged FAKE_TAG."""
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
        ["git", "tag", FAKE_TAG],
    ):
        subprocess.run(command, cwd=clone, capture_output=True, check=True)
    return clone
