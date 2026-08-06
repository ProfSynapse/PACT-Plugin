"""The memory store must never resolve to the operator's real store under test.

WHAT THESE TESTS ARE FOR, because a passing suite is not evidence here. The
suite passed with the leak wide open: 13,812 tests green while 60 of them
opened write-capable connections to the live store. So "the tests pass" cannot
distinguish an isolated system from a leaking one, and every assertion below is
written to FAIL on the pre-fix code rather than to describe the post-fix code.

THE TWO MECHANISMS THAT LEAKED, each with a test here:
  1. IMPORT-TIME BINDING. `config` computed its paths from `Path.home()` when
     the module first imported, so a later redirect reached a value that no
     longer existed to change. Protection depended on import ORDER.
  2. THE PROCESS BOUNDARY. An in-process patch does not survive `exec`, so a
     spawned CLI child resolved the real home however carefully the parent had
     been redirected.

WHAT MUST KEEP WORKING, and it outranks the isolation. Production entry points
that pass no path SHOULD reach the real store: that is what `archive_pin
--index N` does, and `/PACT:prune-memory` keys its refuse-or-proceed decision
on it. A fix that isolates tests by making the default unreachable would refuse
an honest user command, which damages real work rather than merely risking it.
`TestProductionStillResolvesTheRealStore` is that guarantee.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_PARENT = Path(__file__).parent.parent / "skills" / "pact-memory"
sys.path.insert(0, str(SCRIPTS_PARENT))

from scripts.config import (  # noqa: E402
    MEMORY_DIR_ENV,
    get_db_path,
    get_memory_dir,
)

REAL_STORE_SUFFIX = os.path.join(".claude", "pact-memory")

# THE OPERATOR'S TRUE HOME, captured at MODULE IMPORT.
#
# Deliberately bound early, which is the opposite of what the fix does, and for
# a reason that does not apply there: this must be the home as it was BEFORE any
# fixture ran. The sibling autouse fixture `_isolate_config_root_to_tmp` patches
# `Path.home()` to a tmp tree for every test, so calling `Path.home()` inside a
# test yields the REDIRECTED home and an assertion built on it compares a tmp
# path against itself. Module import happens at collection, before any fixture,
# so this is the last honest reading available. `os.path.expanduser` is used
# because it is not the attribute the fixture replaces.
_REAL_HOME = Path(os.path.expanduser("~"))


def _run_child(code: str, env: dict) -> str:
    """Run `code` in a FRESH interpreter and return its stdout, stripped.

    A fresh process is mandatory rather than tidy. The binding under repair is
    evaluated at import, so an in-process check performed after redirecting
    confirms only that the redirect took effect; it cannot observe the defect,
    which is that the value was already fixed before the redirect happened.
    """
    child_env = dict(os.environ)
    child_env.update(env)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=child_env, timeout=60,
    )
    assert result.returncode == 0, f"child failed: {result.stderr}"
    return result.stdout.strip()


_RESOLVE_IN_CHILD = (
    "import sys; sys.path.insert(0, %r)\n"
    "from scripts.config import get_db_path\n"
    "print(get_db_path())\n" % str(SCRIPTS_PARENT)
)


class TestTheConftestLiteralMatchesItsSource:
    """conftest duplicates the variable name; a rename must not un-isolate."""

    def test_conftest_env_name_equals_config_env_name(self):
        """The duplicated literal is pinned to its source.

        `conftest.py` cannot import `scripts.config` at load time without making
        the whole suite depend on that package importing cleanly, so it carries
        its own copy of the name. This test is what makes that copy safe: rename
        `MEMORY_DIR_ENV` without updating conftest and this fails loudly, rather
        than every test silently resolving the operator's real store again.
        """
        import conftest

        assert conftest._MEMORY_DIR_ENV == MEMORY_DIR_ENV, (
            f"conftest isolates on {conftest._MEMORY_DIR_ENV!r} but the resolver "
            f"honours {MEMORY_DIR_ENV!r}. Every test is running against the real "
            f"store. Update conftest._MEMORY_DIR_ENV to match."
        )


class TestTheSessionDefaultIsUnconditional:
    """The collection-time assignment must not honour an inherited value.

    ADDED BECAUSE A MUTATION FOUND THE GAP, not because it was designed in.
    Changing `pytest_configure`'s assignment to `setdefault` and pre-setting
    `PACT_MEMORY_DIR` to the real store left every other test in this file
    GREEN, because the per-test autouse fixture overrides the variable anyway.
    The exposure that survives is narrower and still real: anything resolving
    OUTSIDE a fixture's reach — collection-time imports, session-scoped setup —
    would read the operator's own value and point at the store this exists to
    protect. A contributor who has relocated their store exports that variable.

    STRUCTURAL, AND SAID SO PLAINLY. This inspects source text rather than
    behaviour, because the assignment happens before collection and no test can
    observe the pre-collection state from inside the session. It is a guard
    against reintroducing a known fail-open, not a proof of the runtime property.
    """

    def test_pytest_configure_assigns_rather_than_setdefaults(self):
        import inspect

        import conftest

        source = inspect.getsource(conftest.pytest_configure)
        assert "os.environ[_MEMORY_DIR_ENV] = " in source, (
            "the session-wide memory-store redirect is no longer an "
            "unconditional assignment"
        )
        assert "setdefault(_MEMORY_DIR_ENV" not in source, (
            "`setdefault` honours an inherited PACT_MEMORY_DIR, so a contributor "
            "who has relocated their own store would have collection-time "
            "resolution point at it. The fail direction is ALLOW and it is silent."
        )


class TestResolutionIsLateNotImportTime:
    """Mechanism 1: the value must not be fixed at import."""

    def test_env_change_after_import_still_moves_the_store(self, tmp_path):
        """FAILS PRE-FIX. `config.DB_PATH` was a constant, so a change made
        after import moved nothing."""
        first = get_db_path()
        moved = tmp_path / "relocated"
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(MEMORY_DIR_ENV, str(moved))
            second = get_db_path()
        assert second == moved / "memory.db"
        assert second != first

    def test_home_change_after_import_still_moves_the_store(self, tmp_path):
        """FAILS PRE-FIX, and this is the ORDER-DEPENDENCE test.

        With no override set, the resolver must consult `Path.home()` at CALL
        time. Pre-fix it consulted a value captured at import, so this returned
        the real home no matter what the patch said.
        """
        elsewhere = tmp_path / "elsewhere"
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv(MEMORY_DIR_ENV, raising=False)
            mp.setattr(Path, "home", lambda: elsewhere)
            assert get_memory_dir() == elsewhere / ".claude" / "pact-memory"

    def test_empty_override_is_treated_as_unset(self, tmp_path):
        """An empty value must not relocate the store to a relative path."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(MEMORY_DIR_ENV, "")
            mp.setattr(Path, "home", lambda: tmp_path)
            assert get_memory_dir() == tmp_path / ".claude" / "pact-memory"


class TestRedirectCrossesTheProcessBoundary:
    """Mechanism 2: a child interpreter must inherit the redirect."""

    def test_child_process_honours_the_override(self, tmp_path):
        """FAILS PRE-FIX for every spawned CLI test, which was the larger half
        of the exposure: no in-process patch survives `exec`."""
        target = tmp_path / "child-store"
        out = _run_child(_RESOLVE_IN_CHILD, {MEMORY_DIR_ENV: str(target)})
        assert out == str(target / "memory.db")

    def test_child_process_does_not_reach_the_real_store(self, tmp_path):
        """The property stated as the thing we actually care about."""
        target = tmp_path / "child-store"
        out = _run_child(_RESOLVE_IN_CHILD, {MEMORY_DIR_ENV: str(target)})
        assert out == str(target / "memory.db")
        assert not out.startswith(str(_REAL_HOME / ".claude" / "pact-memory"))


class TestProductionStillResolvesTheRealStore:
    """CARDINAL. Over-block is worse than the leak it would prevent.

    The leak has damaged nothing to date. A refused good-faith command damages
    the user's work immediately, so these tests rank above the isolation ones.
    """

    def test_no_override_resolves_under_the_real_home(self):
        """A production process sets nothing, and must reach the real store."""
        out = _run_child(
            "import sys; sys.path.insert(0, %r)\n"
            "import os\n"
            "os.environ.pop('PACT_MEMORY_DIR', None)\n"
            "from scripts.config import get_db_path\n"
            "print(get_db_path())\n" % str(SCRIPTS_PARENT),
            {},
        )
        expected = _REAL_HOME / ".claude" / "pact-memory" / "memory.db"
        assert out == str(expected), (
            "a production caller that sets no override must still resolve the "
            "real store; refusing it would break `archive_pin --index N`, which "
            "passes no --db-path on purpose"
        )

    def test_resolution_creates_nothing_by_itself(self, tmp_path):
        """Resolving a path must not have side effects.

        `get_db_path` in `config` only computes. Directory creation belongs to
        the callers that intend it, so merely asking where the store is can
        never create a stray tree in someone's home.
        """
        target = tmp_path / "never-created"
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(MEMORY_DIR_ENV, str(target))
            get_db_path()
        assert not target.exists()


class TestTheSuiteIsActuallyIsolatedRightNow:
    """The end-to-end property, asserted from inside the running suite."""

    def test_this_very_test_resolves_away_from_the_real_store(self):
        """If the autouse fixture ever stops working, this fails immediately."""
        resolved = str(get_db_path())
        real = str(_REAL_HOME / ".claude" / "pact-memory")
        assert not resolved.startswith(real), (
            f"this test resolves the memory store to {resolved}, which is the "
            f"operator's real store. The isolation fixture is not working."
        )

    def test_the_override_is_set_for_every_test(self):
        assert os.environ.get(MEMORY_DIR_ENV), (
            "no memory-store override is set, so resolution falls back to the "
            "real home for every test in this run"
        )
