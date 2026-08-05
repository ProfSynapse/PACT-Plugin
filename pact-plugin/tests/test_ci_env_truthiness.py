"""
Location: pact-plugin/tests/test_ci_env_truthiness.py

WHAT THIS PINS
    `memory_init._ci_is_declared()` decides whether
    `check_and_install_dependencies()` takes its `skipped_ci` branch (report
    drift, install nothing) or proceeds to a network `pip install`.

    That decision used to be `os.environ.get('CI')`, which is TRUE for every
    non-empty string — so `CI=false`, `CI=0` and `CI=no` all meant "yes, this
    is CI". The direction was fail-safe (it skipped an install rather than
    performing one unasked), which is why this was a correctness defect rather
    than an urgent one, but the check did not mean what it said.

WHY THE SPELLINGS ARE ENUMERATED RATHER THAN DESCRIBED
    A truthiness bug is invisible in the source: `if os.environ.get('CI')`
    looks exactly like a correct check. Only a case naming a falsy spelling
    distinguishes the two implementations, so the spellings are listed here as
    inputs. A test asserting merely that "CI=true is CI" passes against the
    defect as happily as against the fix.

    The two behavioural arms at the bottom exist for the same reason: they tie
    the predicate to the branch it actually controls, so a future refactor that
    keeps `_ci_is_declared` correct while wiring it up wrongly still fails.

RELATED
    skills/pact-memory/scripts/memory_init.py  the predicate and the branch
    tests/test_memory_init.py                  the CI-branch behaviour tests and
                                               the workflow/package parity guard
"""
import builtins
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), '..', 'skills', 'pact-memory', 'scripts'),
)

from memory_init import _ci_is_declared, check_and_install_dependencies  # noqa: E402

# Spellings that a human or a tool writes when it means "NOT CI". Every one of
# these is a non-empty truthy string except the first, so every one of them was
# read as CI before the fix.
FALSY_SPELLINGS = ["", "0", "false", "no", "False", "FALSE", "No", "  false  "]

# Anything else means CI. `true`/`1` are the common spellings; the rest confirm
# the rule is "not falsy" rather than an allow-list that would miss a variant.
TRUTHY_SPELLINGS = ["true", "1", "yes", "True", "TRUE", "on", "enabled"]


class TestCiPredicate:
    """The predicate in isolation."""

    @pytest.mark.parametrize("value", FALSY_SPELLINGS)
    def test_falsy_spellings_are_not_ci(self, monkeypatch, value):
        monkeypatch.setenv("CI", value)
        assert _ci_is_declared() is False, (
            f"CI={value!r} means NOT CI, but the predicate reported CI. A bare "
            "truthiness check on the environment variable regresses exactly here."
        )

    @pytest.mark.parametrize("value", TRUTHY_SPELLINGS)
    def test_other_values_are_ci(self, monkeypatch, value):
        monkeypatch.setenv("CI", value)
        assert _ci_is_declared() is True, f"CI={value!r} should count as CI"

    def test_unset_is_not_ci(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        assert _ci_is_declared() is False


class TestPredicateIsWiredToTheBranch:
    """
    The predicate is only useful if the drift branch consults it. These two arms
    are a pair on purpose: each alone is satisfied by a constant.
    """

    @staticmethod
    def _import_blocking_one_package():
        """Return an __import__ replacement that hides pysqlite3."""
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'pysqlite3':
                raise ImportError("No module named 'pysqlite3'")
            return original_import(name, *args, **kwargs)

        return mock_import

    def test_ci_true_takes_the_skipped_ci_branch(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        with patch.object(builtins, '__import__', self._import_blocking_one_package()), \
             patch('memory_init.subprocess.run') as mock_run:
            result = check_and_install_dependencies()

        assert result['status'] == 'skipped_ci'
        assert not mock_run.called, "nothing may be installed under CI"

    def test_ci_false_reaches_the_installer_instead(self, monkeypatch):
        """
        The behavioural half of the fix. Before it, `CI=false` returned
        `skipped_ci` and installed nothing — the caller asked for the local
        behaviour and silently got the CI behaviour.
        """
        monkeypatch.setenv("CI", "false")
        with patch.object(builtins, '__import__', self._import_blocking_one_package()), \
             patch('memory_init.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = check_and_install_dependencies()

        assert result['status'] != 'skipped_ci', (
            "CI=false means NOT CI, so the drift branch must not fire"
        )
        assert mock_run.called, (
            "the installer never ran, so CI=false still behaves like CI"
        )
