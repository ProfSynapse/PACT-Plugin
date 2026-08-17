"""Arms for `scripts/verify-gate-tree.sh`.

The script runs the test suite against a DECLARED tree and records which tree
it measured. It exists because a suite capture carried a count and not a tree,
so a run in a different checkout produced a clean summary that certified
nothing about the branch under review.

THE PRIMARY OBLIGATION HERE IS THE NON-REFUSAL SIDE. This script sits on a
merge path. A gate that refuses a faithful run is worse than one that misses a
wrong-tree run, because a noisy red teaches a reader to discount a red, and
that is how a true red goes unnoticed. So the faithful cases below are the
load-bearing arms, and the two refusal cases are the enhancement.

Each faithful case asserts the STAMPS were written, not the pytest exit code.
The temp repositories hold no tests, so pytest exits 5 (nothing collected) on
a faithful run. The discriminator between PROCEEDED and REFUSED is therefore
the capture file: a refusal happens before pytest starts and writes no capture.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "verify-gate-tree.sh"

_REFUSED = 2


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_repo(path: Path) -> Path:
    """Make a git repository with one commit. No tests in it, by design."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--quiet")
    _git(path, "config", "user.email", "arm@example.invalid")
    _git(path, "config", "user.name", "arm")
    (path / "marker.txt").write_text("content\n", encoding="utf-8")
    _git(path, "add", "marker.txt")
    _git(path, "commit", "--quiet", "-m", "seed")
    return path


def _run(declared: str, capture: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_SCRIPT), declared, str(capture), "--collect-only", "-q"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _stamps(capture: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in capture.read_text(encoding="utf-8").splitlines():
        if line.startswith("GATE-"):
            key, _, value = line.partition(" ")
            out[key] = value
    return out


class TestScriptIsPresent:
    def test_script_exists_and_is_executable(self):
        assert _SCRIPT.is_file(), f"missing: {_SCRIPT}"
        assert os.access(_SCRIPT, os.X_OK), f"not executable: {_SCRIPT}"


class TestFaithfulInvocationsAreNotRefused:
    """No faithful case may be refused. This is the cardinal obligation."""

    def test_declared_equals_actual_proceeds_and_stamps(self, tmp_path):
        repo = _make_repo(tmp_path / "repo")
        capture = tmp_path / "capture.txt"

        result = _run(str(repo), capture, repo)

        assert result.returncode != _REFUSED, result.stderr
        assert capture.is_file(), "a faithful run must write a capture"
        stamps = _stamps(capture)
        assert set(stamps) >= {
            "GATE-TREE",
            "GATE-HEAD",
            "GATE-DIRTY-PATHS",
            "GATE-CWD",
            "GATE-COMMAND",
            "GATE-PYTEST-EXIT",
        }, stamps

    def test_stamped_head_is_the_real_head(self, tmp_path):
        """A constant in place of the real sha must not pass."""
        repo = _make_repo(tmp_path / "repo")
        capture = tmp_path / "capture.txt"

        _run(str(repo), capture, repo)

        assert _stamps(capture)["GATE-HEAD"] == _git(repo, "rev-parse", "HEAD")

    def test_stamped_dirty_count_tracks_the_tree(self, tmp_path):
        """A hardcoded zero must not pass. The count moves with the tree."""
        repo = _make_repo(tmp_path / "repo")
        clean_capture = tmp_path / "clean.txt"
        dirty_capture = tmp_path / "dirty.txt"

        _run(str(repo), clean_capture, repo)
        assert _stamps(clean_capture)["GATE-DIRTY-PATHS"] == "0"

        (repo / "marker.txt").write_text("changed\n", encoding="utf-8")
        _run(str(repo), dirty_capture, repo)
        assert _stamps(dirty_capture)["GATE-DIRTY-PATHS"] == "1"

    def test_trailing_slash_on_declared_path_proceeds(self, tmp_path):
        repo = _make_repo(tmp_path / "repo")
        capture = tmp_path / "capture.txt"

        result = _run(str(repo) + "/", capture, repo)

        assert result.returncode != _REFUSED, result.stderr
        assert capture.is_file()

    def test_relative_declared_path_proceeds(self, tmp_path):
        repo = _make_repo(tmp_path / "repo")
        sub = repo / "sub"
        sub.mkdir()
        capture = tmp_path / "capture.txt"

        result = _run("..", capture, sub)

        assert result.returncode != _REFUSED, result.stderr
        assert capture.is_file()

    def test_symlinked_spelling_of_one_tree_proceeds(self, tmp_path):
        """One tree spelled two ways must not read as two trees."""
        repo = _make_repo(tmp_path / "repo")
        link = tmp_path / "link"
        link.symlink_to(repo, target_is_directory=True)
        capture = tmp_path / "capture.txt"

        result = _run(str(link), capture, repo)

        assert result.returncode != _REFUSED, result.stderr
        assert capture.is_file()

    def test_absent_capture_directory_is_made_rather_than_refused(self, tmp_path):
        repo = _make_repo(tmp_path / "repo")
        capture = tmp_path / "absent" / "deeper" / "capture.txt"

        result = _run(str(repo), capture, repo)

        assert result.returncode != _REFUSED, result.stderr
        assert capture.is_file()

    def test_detached_head_proceeds(self, tmp_path):
        """The continuous-integration checkout shape. A detached HEAD is faithful."""
        repo = _make_repo(tmp_path / "repo")
        _git(repo, "checkout", "--detach", "HEAD", "--quiet")
        capture = tmp_path / "capture.txt"

        result = _run(str(repo), capture, repo)

        assert result.returncode != _REFUSED, result.stderr
        assert capture.is_file()


class TestWrongTreeIsRefused:
    """The catching leg. It must refuse BEFORE pytest starts."""

    def test_a_different_tree_is_refused_with_no_capture(self, tmp_path):
        declared = _make_repo(tmp_path / "declared")
        other = _make_repo(tmp_path / "other")
        capture = tmp_path / "capture.txt"

        result = _run(str(declared), capture, other)

        assert result.returncode == _REFUSED, result.stdout
        assert not capture.exists(), "a refusal must not leave a capture behind"
        assert "GATE REFUSED" in result.stderr
        assert str(declared.resolve()) in result.stderr
        assert str(other.resolve()) in result.stderr

    def test_a_non_repository_tree_is_refused_with_a_route(self, tmp_path):
        """A refusal with no route is a dead end, and a dead end retires the gate."""
        declared = _make_repo(tmp_path / "declared")
        export = tmp_path / "export"
        export.mkdir()
        capture = tmp_path / "capture.txt"

        result = _run(str(declared), capture, export)

        assert result.returncode == _REFUSED, result.stdout
        assert not capture.exists()
        assert "python3 -m pytest" in result.stderr, (
            "the refusal must name what to run instead"
        )

    def test_a_declared_path_that_is_not_a_directory_is_refused(self, tmp_path):
        repo = _make_repo(tmp_path / "repo")
        capture = tmp_path / "capture.txt"

        result = _run(str(tmp_path / "no-such-path"), capture, repo)

        assert result.returncode == _REFUSED, result.stdout
        assert not capture.exists()


class TestUsage:
    @pytest.mark.parametrize("argv", [[], ["only-one"]])
    def test_too_few_arguments_reports_usage(self, argv):
        result = subprocess.run(
            ["bash", str(_SCRIPT), *argv],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr
