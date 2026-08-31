"""
Location: pact-plugin/tests/test_lint_check_files_mode.py
Summary: Subprocess contract tests for lint-check.sh --files mode (the
         consumer-facing tier of the import-hygiene ladder): the three
         verdict outcomes and their exit codes, the crash-honesty guard
         (a checker crash degrades to SKIPPED, never a phantom FINDINGS),
         and the missing-path pre-filter.
Used by: pytest suite. The predicate these rungs call is covered in
         test_check_unused_imports.py; the dev-repo strict-tier gate lives
         in test_import_hygiene.py. THIS file pins the shell contract that
         coder dispatch prose relies on: the LAST stdout line is exactly one
         verdict, and exit 1 means real findings — nothing else.

Scope boundary — --files mode ONLY:
    The legacy whole-tree directory mode (reached by passing a directory
    instead of --files) is a separate mode with separate ownership and is
    deliberately NOT pinned here. Everything below invokes the script with
    --files as the first argument, which returns before the legacy mode's
    `set -e` is ever enabled.

Determinism across environments:
    Rows that expect findings use a module-level unused import, which every
    rung of the ladder (ruff, pyflakes, flake8, stdlib fallback) reports as
    exactly one path:line-format line — so the verdict and count assertions
    hold no matter which rung wins on the host. The crash-guard row controls
    the ladder explicitly through PATH: a fake ruff that passes its execution
    probe and then crashes, plus a fake python3 that fails every probe, so
    no real rung can run and the fail-open degradation path is forced.
"""

import os
import stat
import subprocess
from pathlib import Path

_SCRIPT = (
    Path(__file__).parent.parent
    / "skills"
    / "pact-coding-standards"
    / "scripts"
    / "lint-check.sh"
)

def _run(*argv, env=None):
    return subprocess.run(
        ["bash", str(_SCRIPT), "--files", *argv],
        capture_output=True,
        text=True,
        env=env,
    )


def _last_stdout_line(proc):
    lines = [line for line in proc.stdout.splitlines() if line]
    assert lines, f"no stdout at all (stderr: {proc.stderr!r})"
    return lines[-1]


_UNRESOLVED = "IMPORT-HYGIENE: SKIPPED (arguments given but none is a checkable .py file)"
_NO_FILES = "IMPORT-HYGIENE: SKIPPED (no Python files given)"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class TestVerdictContract:
    """The three verdict outcomes: every invocation ends in exactly one
    verdict as the LAST stdout line, with the documented exit code."""

    def test_clean_file_pass_exit_zero(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("import os\nprint(os.sep)\n", encoding="utf-8")
        proc = _run(str(f))
        assert proc.returncode == 0
        assert _last_stdout_line(proc) == "IMPORT-HYGIENE: PASS"

    def test_findings_exit_one_verdict_last(self, tmp_path):
        f = tmp_path / "dirty.py"
        f.write_text("import os\n", encoding="utf-8")
        proc = _run(str(f))
        assert proc.returncode == 1
        assert _last_stdout_line(proc) == "IMPORT-HYGIENE: FINDINGS (1)"
        # The finding itself is on stdout above the verdict, in the shared
        # path:line format every rung of the ladder emits.
        assert f"{f}:1" in proc.stdout

    def test_non_py_argument_degrades_gracefully_at_exit_zero(self, tmp_path):
        """A non-.py argument is a caller-argument mistake, not a finding.

        This arm previously asserted the no-files verdict for this input,
        which pinned the silent-drop defect as expected behaviour. The input
        is unchanged; only the expected verdict moved, because a discarded
        argument is not the same state as no argument.
        """
        f = tmp_path / "notes.txt"
        f.write_text("not python\n", encoding="utf-8")
        proc = _run(str(f))
        assert proc.returncode == 0
        assert _last_stdout_line(proc) == _UNRESOLVED


class TestUnresolvedPathsVerdict:
    """Three states all end in a SKIPPED verdict and must stay DISTINCT.

    Collapsing any two is how a malformed invocation came to read as a clean
    check: a caller whose shell did not word-split a quoted file list passes
    ONE argument, "a.py b.py c.py". It ends in .py so the *.py filter matches,
    then fails the existence test, leaving nothing to check — and the verdict
    said "no Python files given", which was false and pass-shaped.

    Each case below reaches its verdict for a DIFFERENT reason, named beside
    it. A mutation merging two branches reddens at least one of them, and no
    two cases share the set of mutations that redden them -- that separation,
    not any fixed count, is what keeps the states distinct:
      (a) no arguments at all             -> test_zero_arguments_*
      (b) arguments that exist, none .py  -> test_no_python_files_skipped_exit_zero
                                             (in TestVerdictContract above)
      (c) .py-shaped arguments, none exist -> the two cases here
    """

    def test_zero_arguments_keeps_legacy_skipped(self):
        # Reason: nothing was passed, so the *.py filter never runs and
        # nothing is dropped. The legacy verdict is CORRECT here.
        proc = _run()
        assert proc.returncode == 0
        assert _last_stdout_line(proc) == _NO_FILES

    def test_unsplit_file_list_reports_unresolved_not_no_files(self, tmp_path):
        # Reason: ONE .py-suffixed argument that does not exist — the exact
        # shape a caller produces by passing "$FILES" unsplit. Both real
        # files exist, so this is not a missing-file case: it is the JOINED
        # string failing to resolve.
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("import os\nprint(os.sep)\n", encoding="utf-8")
        b.write_text("import os\nprint(os.sep)\n", encoding="utf-8")

        proc = _run(f"{a} {b}")  # one argv entry, space-joined

        assert a.exists() and b.exists()
        assert proc.returncode == 0
        assert _last_stdout_line(proc) == _UNRESOLVED

    def test_non_py_argument_is_not_reported_as_nothing_given(self, tmp_path):
        """A discarded argument must not read as "you passed nothing".

        Without the case statement's else arm a non-.py argument was dropped
        silently -- uncounted, unreported -- and the run fell through to the
        no-files verdict. That collapses two states a reader must tell apart:
        the caller who passed nothing, and the caller whose arguments were all
        thrown away. The stderr assertion is the load-bearing half; a verdict
        check alone would also pass against the silent version.
        """
        proc = _run(str(tmp_path / "notes.txt"))

        assert _last_stdout_line(proc) == _UNRESOLVED, (
            f"a non-.py argument reached {_last_stdout_line(proc)!r}. If that "
            f"is the no-files verdict, the argument was discarded silently and "
            f"the caller cannot tell it from passing nothing at all."
        )
        assert "not a .py path" in proc.stderr, (
            f"nothing on stderr named the discarded argument: {proc.stderr!r}"
        )

    def test_existing_directory_is_not_reported_as_absent(self, tmp_path):
        """An existing directory and an absent path are different states.

        Both fail `-f` and share one verdict, so the discrimination lives on
        stderr. If these two produce the same line, a caller who passed a real
        directory is told their path does not exist.
        """
        package = tmp_path / "pkg.py"
        package.mkdir()

        present = _run(str(package))
        absent = _run(str(tmp_path / "ghost.py"))

        assert "not a regular file" in present.stderr, (
            f"an existing directory was not distinguished: {present.stderr!r}"
        )
        assert "skipping missing path" in absent.stderr, (
            f"an absent path was not distinguished: {absent.stderr!r}"
        )
        assert present.stderr != absent.stderr, (
            "an existing directory and an absent path emitted identical "
            "stderr, so the two states are indistinguishable to a caller."
        )

    def test_lone_ghost_path_reports_unresolved(self, tmp_path):
        # Reason: a .py path that genuinely does not exist, as the ONLY
        # argument. Same branch as the case above but with no space in it,
        # so a fix that keyed on "argument contains a space" would pass that
        # one and fail this. Distinct from TestMissingPathPrefilter, where a
        # real file survives alongside the ghost.
        proc = _run(str(tmp_path / "ghost.py"))
        assert proc.returncode == 0
        assert _last_stdout_line(proc) == _UNRESOLVED


class TestOnlyNamedFilesAreChecked:
    """A directory named `*.py` must not smuggle its contents into the check.

    The header contract is that only the files named on the command line are
    checked. A directory passes the `*.py` suffix filter, and an existence test
    that accepts any directory entry lets the checker recurse into it, so a
    finding surfaces from a file the caller never named -- with a path the
    caller cannot account for. A regular-file test is what keeps the contract
    and the behaviour the same thing.
    """

    def test_a_directory_named_like_a_module_yields_no_findings(self, tmp_path):
        package = tmp_path / "notamodule.py"
        package.mkdir()
        # An unused import: every rung of the ladder reports this one.
        (package / "inner.py").write_text("import os\n", encoding="utf-8")

        proc = _run(str(package))

        assert proc.returncode == 0, (
            f"a directory named like a module produced exit {proc.returncode}. "
            f"Exit 1 means the checker recursed into it and reported findings "
            f"from a file that was never named. stdout={proc.stdout!r}"
        )
        assert "FINDINGS" not in proc.stdout, (
            f"findings surfaced from inside a directory that was merely named "
            f"on the command line: {proc.stdout!r}"
        )


class TestCrashHonestyGuard:
    """An unhandled checker exception also exits 1 — exit code alone must
    never be read as findings. A rung that exits 1 WITHOUT a single
    path:line-format output line is a crash: the ladder notes it on stderr,
    tries the next rung, and when nothing usable remains it fails OPEN with
    a SKIPPED verdict — never a phantom FINDINGS block."""

    def test_checker_crash_degrades_to_skipped_not_findings(self, tmp_path):
        fakebin = tmp_path / "fakebin"
        fakebin.mkdir()
        # Passes the execution probe, then "crashes": exit 1 with
        # traceback-shaped output that contains no path:line: token.
        _write_executable(
            fakebin / "ruff",
            "#!/bin/bash\n"
            'if [ "$1" = "--version" ]; then echo fake-ruff; exit 0; fi\n'
            'echo "Traceback (most recent call last)"\n'
            'echo "SomeError: boom"\n'
            "exit 1\n",
        )
        # Fails every probe, so no python3-based rung (pyflakes, flake8,
        # stdlib fallback) can run at all.
        _write_executable(fakebin / "python3", "#!/bin/bash\nexit 9\n")

        target = tmp_path / "dirty.py"
        target.write_text("import os\n", encoding="utf-8")

        env = dict(os.environ)
        env["PATH"] = f"{fakebin}:{env['PATH']}"
        proc = _run(str(target), env=env)

        assert proc.returncode == 0
        assert _last_stdout_line(proc) == (
            "IMPORT-HYGIENE: SKIPPED (no usable import checker on this system)"
        )
        assert "FINDINGS" not in proc.stdout
        # The crash is loud on stderr, not silently swallowed.
        assert "failed (exit 1)" in proc.stderr
        assert "trying next checker" in proc.stderr


class TestMissingPathPrefilter:
    """Paths that no longer exist (deleted/renamed in the same change set)
    are dropped with a stderr note; the remaining files still get checked,
    and the verdict reflects only the real files."""

    def test_ghost_path_noted_and_rest_still_checked(self, tmp_path):
        ghost = tmp_path / "ghost.py"  # never created
        dirty = tmp_path / "dirty.py"
        dirty.write_text("import os\n", encoding="utf-8")

        proc = _run(str(ghost), str(dirty))

        assert proc.returncode == 1
        assert "skipping missing path" in proc.stderr
        assert str(ghost) in proc.stderr
        assert _last_stdout_line(proc) == "IMPORT-HYGIENE: FINDINGS (1)"
        assert f"{dirty}:1" in proc.stdout
