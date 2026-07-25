"""The REAL CLAUDE.md resolution path for archive_pin — driven, not mocked.

THIS FILE EXISTS BECAUSE NOTHING ELSE EXERCISES THE ACTUAL RESOLVER.
`get_project_claude_md_path` is monkeypatched in both places it appears
(test_check_pin_caps.py's `patched_claude_md`, test_archive_pin.py's
`claude_md` fixture), so every existing test hands the code a path it already
decided on. That is precisely why a resolver defect survived PREPARE,
ARCHITECT, CODE, TEST and three reviews: no test could see it, because no
test ever asked the resolver a question.

So nothing here patches `get_project_claude_md_path`, `resolve_claude_md`, or
`_resolve_project_claude_md_with_base`. The tests set `CLAUDE_PROJECT_DIR`
and the working directory — the two real inputs — and let resolution run.

THE DEFECT UNDER TEST. Resolution order is CLAUDE_PROJECT_DIR -> git
common-dir parent -> CWD, and a miss at any step falls through SILENTLY. A
CLAUDE_PROJECT_DIR naming a directory with no CLAUDE.md therefore does not
fail; it resolves to a DIFFERENT project's file and the archival reports a
confident success for a pin the invocation never named. The command's Step 3
heading cross-check is structurally blind to it, because check_pin_caps.py
uses the SAME resolver — the listing step and the archival step agree on the
same wrong file and every heading matches. That check catches an index shift
WITHIN a file; nothing catches a wrong FILE.

WHY THE REFUSAL IS NARROW, and why that matters more than making it strict.
PACT's own primary workflow sets CLAUDE_PROJECT_DIR to a WORKTREE, where
CLAUDE.md is gitignored and therefore absent, and depends on the git
fall-through to reach the main checkout's file. A blanket "env dir has no
CLAUDE.md -> refuse" rule would break that on every single invocation — a
cardinal over-block. `test_same_repository_fallthrough_is_allowed` is the
guard on that, and it is the more important half of this file.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import archive_pin  # noqa: E402


PINNED = (
    "# Project\n\n## Pinned Context\n\n"
    "<!-- pinned: 2026-01-01 -->\n"
    "### {title}\n"
    "body of {title}\n"
)


def _make_project(root: Path, title, layout="dot_claude"):
    """Create a project dir; `title=None` means NO CLAUDE.md at all."""
    root.mkdir(parents=True, exist_ok=True)
    if title is None:
        return root
    if layout == "dot_claude":
        target = root / ".claude" / "CLAUDE.md"
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        target = root / "CLAUDE.md"
    target.write_text(PINNED.format(title=title), encoding="utf-8")
    return root


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A tmpdir guaranteed to be OUTSIDE any git repository.

    Without this the git fall-through could reach the PACT repo itself and
    quietly supply a real CLAUDE.md, which would make these tests measure the
    developer's checkout instead of the fixture. Asserted, not assumed.
    """
    probe = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, timeout=10,
    )
    assert probe.returncode != 0, (
        f"tmp_path is inside a git repo ({probe.stdout.strip()}) — the git "
        "fall-through would reach a real CLAUDE.md and these tests would "
        "measure the checkout, not the fixture"
    )
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return tmp_path


class TestResolutionIsDriven:
    """Controls first: the resolver must behave correctly when it is right,
    or a later refusal proves nothing about discrimination."""

    def test_env_dir_with_claude_md_is_used(self, isolated, monkeypatch):
        a = _make_project(isolated / "project_a", "PIN A")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
        monkeypatch.chdir(a)
        path, base = archive_pin.resolve_claude_md()
        assert path == a / ".claude" / "CLAUDE.md"
        assert "### PIN A" in path.read_text(encoding="utf-8")
        assert Path(base) == a

    def test_legacy_layout_is_used(self, isolated, monkeypatch):
        a = _make_project(isolated / "legacy", "PIN L", layout="legacy")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
        monkeypatch.chdir(a)
        path, _ = archive_pin.resolve_claude_md()
        assert path == a / "CLAUDE.md"

    def test_no_claude_md_anywhere_is_unevaluable(self, isolated, monkeypatch):
        empty = _make_project(isolated / "empty", None)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(empty))
        monkeypatch.chdir(empty)
        with pytest.raises(archive_pin._Unevaluable) as exc:
            archive_pin.resolve_claude_md()
        assert "not found" in exc.value.reason


class TestCrossProjectFallthroughIsRefused:
    """THE F-B GUARD. Fails on the pre-fix code, which returned project_a's
    file for an invocation that named project_b."""

    def test_cross_project_fallthrough_raises(self, isolated, monkeypatch):
        a = _make_project(isolated / "project_a", "PIN A")
        b = _make_project(isolated / "project_b", None)
        # Precondition, asserted so the test cannot pass for the wrong reason:
        # b must genuinely have no CLAUDE.md, or there is no fall-through.
        assert not (b / "CLAUDE.md").exists()
        assert not (b / ".claude" / "CLAUDE.md").exists()

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(b))
        monkeypatch.chdir(a)

        with pytest.raises(archive_pin._Unevaluable) as exc:
            archive_pin.resolve_claude_md()
        reason = exc.value.reason
        assert str(b) in reason, "refusal must name the directory that was set"
        assert "different project" in reason
        assert "project_a" in reason, (
            "refusal must name the file it would otherwise have used, or the "
            "curator cannot tell what was about to happen"
        )

    def test_the_fallthrough_target_really_was_reachable(
        self, isolated, monkeypatch
    ):
        """NON-VACUITY CONTROL for the test above.

        The refusal is only meaningful if resolution WOULD have succeeded on
        the wrong file. Drive the underlying resolver directly — the one
        `resolve_claude_md` wraps — and confirm it happily returns project_a
        while the environment names project_b. If this ever stops returning a
        path, the test above would pass because nothing resolved at all,
        which is a different and much safer world.
        """
        a = _make_project(isolated / "project_a", "PIN A")
        b = _make_project(isolated / "project_b", None)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(b))
        monkeypatch.chdir(a)

        path, _base = archive_pin._resolve_project_claude_md_with_base()
        assert path is not None, "no fall-through occurred — refusal is moot"
        assert "PIN A" in path.read_text(encoding="utf-8"), (
            "the unguarded resolver did NOT return the other project's file, "
            "so this suite is no longer testing the defect it was written for"
        )


class TestSameRepositoryFallthroughIsAllowed:
    """THE OVER-BLOCK GUARD, and the more important half of this file.

    PACT sets CLAUDE_PROJECT_DIR to a worktree where CLAUDE.md is gitignored
    and absent, and relies on the git fall-through to reach the main
    checkout. If the refusal above were written as "env dir has no CLAUDE.md
    -> refuse", it would fire on every PACT invocation. This proves it does
    not.
    """

    def test_same_repository_fallthrough_is_allowed(
        self, isolated, monkeypatch
    ):
        repo = isolated / "repo"
        _make_project(repo, "PIN ROOT")
        init = subprocess.run(["git", "init", "-q", str(repo)],
                              capture_output=True, text=True, timeout=30)
        assert init.returncode == 0, f"git init failed: {init.stderr}"

        # A subdirectory of the SAME repo, with no CLAUDE.md of its own --
        # structurally the worktree case: env names it, resolution falls
        # through to the repo root, and the root is the same project.
        sub = repo / "subproject"
        sub.mkdir()
        assert not (sub / "CLAUDE.md").exists()

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(sub))
        monkeypatch.chdir(sub)

        path, base = archive_pin.resolve_claude_md()   # must NOT raise
        assert "PIN ROOT" in path.read_text(encoding="utf-8")
        assert Path(base).resolve() == repo.resolve()

    def test_same_repository_predicate_is_true_for_a_subdir(
        self, isolated
    ):
        """The discriminator itself, tested directly."""
        repo = isolated / "repo2"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)],
                       capture_output=True, timeout=30)
        sub = repo / "nested"
        sub.mkdir()
        assert archive_pin._same_repository(sub, repo) is True

    def test_same_repository_predicate_is_false_across_repos(self, isolated):
        one = isolated / "one"; one.mkdir()
        two = isolated / "two"; two.mkdir()
        subprocess.run(["git", "init", "-q", str(one)],
                       capture_output=True, timeout=30)
        subprocess.run(["git", "init", "-q", str(two)],
                       capture_output=True, timeout=30)
        assert archive_pin._same_repository(one, two) is False

    def test_same_repository_predicate_fails_safe_outside_git(self, isolated):
        """A non-repo directory returns False, routing to a refusal. On a
        destructive path, declining to guess is the safe direction."""
        plain = isolated / "plain"; plain.mkdir()
        assert archive_pin._same_repository(plain, plain) is False


class TestSymlinkedClaudeMdAttribution:
    """FOLDED IN from the implementation review's symlink Minor — same defect
    family as F-B: a resolver producing a plausible wrong answer with no
    signal.

    The archive's project is now taken from the resolver's own `base` (the
    directory it found the file under, captured BEFORE descending into
    `.claude`) rather than re-derived from the returned path with `.resolve()`,
    which followed a leaf symlink and attributed the archive to the link
    target's parent.
    """

    def test_symlinked_claude_md_attributes_to_the_project_not_the_target(
        self, isolated, monkeypatch
    ):
        """Asserts on the CWD `archive_pin` actually hands the memory CLI,
        NOT on the resolver's base.

        The first version of this test checked `resolve_claude_md()[1]` and
        passed against the pre-fix code — the resolver's base was always
        right; what was wrong was `archive_pin` re-deriving the project from
        the leaf path instead of using that base. Testing the resolver
        measured the correct property on the wrong object, which is the same
        mistake this whole feature exists to catch. The mutation sweep caught
        it: reverting the attribution left the suite green.

        The memory layer detects `project_id` from CLAUDE_PROJECT_DIR, else
        git, else by walking up from the CWD — so the cwd handed to the
        subprocess IS the archive's project attribution.
        """
        proj = isolated / "myproject"; proj.mkdir()
        store = isolated / "elsewhere"; store.mkdir()
        real = store / "CLAUDE.md"
        real.write_text(PINNED.format(title="PIN S"), encoding="utf-8")
        os.symlink(real, proj / "CLAUDE.md")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
        monkeypatch.chdir(proj)

        seen = {}

        def _spy(args, db_path=None, stdin_data=None, cwd=None):
            seen["cwd"] = cwd
            if args[0] == "save":
                return 0, json.dumps(
                    {"ok": True, "result": {"memory_id": "a" * 32}}
                ), ""
            return 0, json.dumps(
                {"ok": True, "result": {"context": stdin_data or ""}}
            ), ""

        monkeypatch.setattr(archive_pin, "_run_memory_cli", _spy)
        archive_pin.build_verdict(0)

        assert seen, "the memory CLI was never invoked — nothing was measured"
        assert Path(seen["cwd"]).name == "myproject", (
            f"archive filed under {Path(seen['cwd']).name!r} — the symlink "
            f"TARGET's directory — rather than the project that owns the pin"
        )


class TestVerdictCarriesTheResolvedPath:
    """`claude_md_path` in every verdict, so a wrong file is visible.

    A boolean 'resolved ok' would reproduce the defect exactly: correct-
    looking and silent about WHICH file. The curator has to be able to read
    the literal path and recognise it.
    """

    def test_unevaluable_from_bad_index_still_names_the_file(
        self, isolated, monkeypatch
    ):
        a = _make_project(isolated / "project_a", "PIN A")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
        monkeypatch.chdir(a)
        verdict = archive_pin.build_verdict(99)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert verdict["claude_md_path"] is not None
        assert "project_a" in verdict["claude_md_path"]

    def test_unresolvable_reports_null_path_not_a_guess(
        self, isolated, monkeypatch
    ):
        empty = _make_project(isolated / "empty", None)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(empty))
        monkeypatch.chdir(empty)
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert verdict["claude_md_path"] is None, (
            "null means no file was resolved; inventing a path here would be "
            "worse than reporting none"
        )

    def test_archived_verdict_names_the_file(self, isolated, monkeypatch,
                                             tmp_path):
        a = _make_project(isolated / "project_a", "PIN A")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
        monkeypatch.chdir(a)
        verdict = archive_pin.build_verdict(
            0, db_path=str(tmp_path / "mem.db")
        )
        assert verdict["outcome"] == "ARCHIVED", verdict
        assert verdict["claude_md_path"] == str(
            (a / ".claude" / "CLAUDE.md")
        ), verdict["claude_md_path"]

    def test_cli_emits_the_path_as_json(self, isolated, monkeypatch, capsys):
        a = _make_project(isolated / "project_a", "PIN A")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
        monkeypatch.chdir(a)
        rc = archive_pin.main(["--index", "99"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert "claude_md_path" in payload
