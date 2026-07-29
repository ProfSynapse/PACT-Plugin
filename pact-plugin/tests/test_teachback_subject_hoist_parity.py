"""Hoist parity: `_is_teachback_subject` was moved from task_lifecycle_gate.py
to shared/task_utils.py (as the public `is_teachback_subject`) so a second hook
surface — the handoff_ordering_gate PreToolUse WARN — can reuse the predicate
without importing the sibling PostToolUse gate module.

These tests pin three properties the hoist must preserve:

  1. SINGLE DEFINITION — the gate re-imports the shared function (its
     `_is_teachback_subject` IS `task_utils.is_teachback_subject`), and the
     canonical regex `_TEACHBACK_SUBJECT_PATTERN` is NOT duplicated back into
     the gate source. Duplication would reopen the drift class the structural
     match was introduced to close.
  2. BEHAVIORAL PARITY — the shared function returns the same verdict the gate's
     predicate always returned across canonical / non-canonical / non-string
     inputs (the move is behavior-preserving, not a re-spec).
  3. PURITY — never raises on hostile input (mirrors the pre-hoist contract).

A fourth property is pinned below, added when the pattern's tail was widened
from the literal `TEACHBACK for ` to a word boundary:

  4. WORD-BOUNDARY TAIL — a gate that qualifies the marker before the mission
     (`preparer: TEACHBACK (respawn) for …`) matches, while the marker must
     still stand as its own word (`TEACHBACKS` does not). Every subject the
     strict trailing-space form matched still matches: the widening is a
     superset, never a re-aim.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import task_lifecycle_gate as tlg  # noqa: E402
from shared.task_utils import is_teachback_subject  # noqa: E402


# Canonical Teachback subjects (must return True) and near-misses (False).
# The near-misses pin the structural-match rationale: a bare substring check
# would false-fire on planning/discussion subjects that merely contain the word.
_TRUE_CASES = [
    "devops: TEACHBACK for journal-durability",
    "backend-coder-2: TEACHBACK for #880 CODE",
    "architect-1: TEACHBACK for the redesign",
    "secretary: TEACHBACK for consolidation",
]
_FALSE_CASES = [
    "Plan: wake-lifecycle teachback re-arm fix",   # substring, not anchored shape
    "devops: implement Fix A",                      # work task, no TEACHBACK
    "TEACHBACK for x",                              # missing the `<name>:` prefix
    "Devops: TEACHBACK for x",                      # uppercase name (pattern is [a-z0-9-])
    "devops:TEACHBACK for x",                       # missing the space after colon
    "",                                             # empty
]

# The historical trailing-space tail, kept ONLY as a fixture control: each
# widened case below must fail THIS pattern, which is what makes it a genuine
# widening case rather than a subject the strict form already matched.
_STRICT_TRAILING_SPACE_PATTERN = re.compile(r"^[a-z0-9-]+: TEACHBACK for ")

# Real gate shapes the strict trailing-space form silently missed. The first is
# not hypothetical — it is a subject that shipped and escaped the carve-out.
_WIDENED_TRUE_CASES = [
    "preparer: TEACHBACK (respawn) for ste100-plugin",
    "coder-a: TEACHBACK — C-1 + C-9",
    "architect: TEACHBACK",
]

# The boundary itself. A widening that dropped `\b` (a bare `TEACHBACK` prefix)
# would turn these True, so they pin the tail's SHAPE, not merely its looseness.
_WORD_BOUNDARY_FALSE_CASES = [
    "devops: TEACHBACKS for x",
    "devops: TEACHBACKING the plan",
]


class TestSingleDefinition:
    def test_gate_alias_is_the_shared_function(self):
        """The gate's `_is_teachback_subject` must BE the hoisted shared
        function — same object, proving the re-import (not a re-definition)."""
        assert tlg._is_teachback_subject is is_teachback_subject

    def test_regex_not_duplicated_in_gate_source(self):
        """The canonical pattern lives ONLY in task_utils — the gate source
        must NOT re-introduce `_TEACHBACK_SUBJECT_PATTERN` (single-definition
        pin against the drift class)."""
        gate_src = Path(tlg.__file__).read_text(encoding="utf-8")
        # Allow the explanatory hoist comment to NAME the symbol, but there must
        # be NO assignment (`_TEACHBACK_SUBJECT_PATTERN = re.compile(...)`).
        assert not re.search(r"^_TEACHBACK_SUBJECT_PATTERN\s*=", gate_src, re.MULTILINE), (
            "the teachback regex must not be duplicated back into the gate; "
            "single definition lives in shared/task_utils.py"
        )


class TestBehavioralParity:
    @pytest.mark.parametrize("subject", _TRUE_CASES)
    def test_canonical_subjects_match(self, subject):
        assert is_teachback_subject(subject) is True
        assert tlg._is_teachback_subject(subject) is True

    @pytest.mark.parametrize("subject", _FALSE_CASES)
    def test_non_canonical_subjects_do_not_match(self, subject):
        assert is_teachback_subject(subject) is False
        assert tlg._is_teachback_subject(subject) is False


class TestWordBoundaryTail:
    """The tail is a word boundary, not the literal `TEACHBACK for `."""

    @pytest.mark.parametrize("subject", _WIDENED_TRUE_CASES)
    def test_qualified_marker_matches(self, subject):
        # Fixture control FIRST: assert the case is genuinely one the strict
        # form missed. Without this, a case that the old pattern already
        # matched would pass while proving nothing about the widening.
        assert _STRICT_TRAILING_SPACE_PATTERN.match(subject) is None, (
            f"fixture error: {subject!r} matches the strict trailing-space "
            "form, so it cannot demonstrate the widening"
        )
        assert is_teachback_subject(subject) is True
        assert tlg._is_teachback_subject(subject) is True

    @pytest.mark.parametrize("subject", _WORD_BOUNDARY_FALSE_CASES)
    def test_marker_must_stand_as_its_own_word(self, subject):
        assert is_teachback_subject(subject) is False, (
            f"{subject!r} must NOT read as a teachback gate — the tail is a "
            r"word boundary (\b), not a bare `TEACHBACK` prefix"
        )
        assert tlg._is_teachback_subject(subject) is False

    @pytest.mark.parametrize("subject", _TRUE_CASES)
    def test_widening_is_a_superset_of_the_strict_form(self, subject):
        """Nothing the strict trailing-space form matched may stop matching:
        the widening only ADDS subjects to the teachback carve-out."""
        assert _STRICT_TRAILING_SPACE_PATTERN.match(subject) is not None
        assert is_teachback_subject(subject) is True


class TestPurity:
    @pytest.mark.parametrize("bad", [None, 123, [], {}, object()])
    def test_non_string_input_returns_false_never_raises(self, bad):
        assert is_teachback_subject(bad) is False
