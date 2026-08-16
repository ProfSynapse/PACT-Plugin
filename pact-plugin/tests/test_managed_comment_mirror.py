"""
Location: pact-plugin/tests/test_managed_comment_mirror.py

Summary: Enforces that the two managed-section comment strings are IDENTICAL
across the SOURCE TEXT of the three modules that carry them. `working_memory.py`
holds the named constants; `session_resume.py` and `claude_md_manager.py` repeat
the same text in different syntactic shapes.

WHAT THIS FILE ENFORCES, AND WHAT IT CANNOT SEE. IT ENFORCES TEXT IDENTITY
ACROSS THREE FILES. IT CANNOT SEE WHICH FUNCTION EMITS. It reads two things and
no others: a MODULE-LEVEL assignment in the SSOT, by AST, and a SUBSTRING of the
RAW SOURCE of each mirror. Nothing here inspects a function body, a call site,
or an emission. So an emitter that STOPS EMITTING leaves this gate green for as
long as the constants stay defined, and that is not hypothetical: MEASURED, four
of the five emitters in this family are invisible here.

THE CAUSE IS A SEPARATION, AND THE SEPARATION IS CORRECT IN ITSELF. The two
comments were once literals inside the creation template of
`claude_md_manager.py`, so deletion of an emission also deleted the text and
this gate reddened BY ACCIDENT. Extracting them to module constants split the
DEFINITION from the USE. This gate reads the definition.
`session_resume.py` is the one mirror for which source-text presence continues
to track emission, and only because the literal IS the emission there. That is
an accident of spelling rather than a mechanism, so do not read it as coverage
of the other two files.

THE BEHAVIOURAL HALF LIVES IN `tests/test_managed_comment_emitted.py`, which
RUNS each emitter and asserts the emitted region. The two files have different
subjects on purpose and neither replaces the other. This one compares files to
each other and needs no fixture. That one compares output to the SSOT.

Used by/with:
- skills/pact-memory/scripts/working_memory.py: the named constants. THIS FILE
  IS THE SSOT, and `_SSOT` below names it and nothing else.
- hooks/shared/session_resume.py: a MIRROR. It repeats both literals inside a
  concatenation.
- hooks/shared/claude_md_manager.py: a MIRROR, and at the same time the
  HOOKS-SIDE ORIGIN, which is the one spelling inside `hooks/` that
  `session_resume.py` imports from.
- tests/test_managed_comment_emitted.py: the behavioural sibling described
  above.

WHY A TEST AND NOT A COMMENT. `working_memory.py` carries a prose instruction to
"Change all three in ONE commit", and warns that fixing two of three converts one
consistent falsehood into a three-way disagreement. That is a CLAIM, not an
ENFORCEMENT, and the difference is the subject of the change set this test ships
with. Nothing executed that sentence.

THE INCIDENTAL COVERAGE IS WEAKER THAN IT LOOKS, WHICH IS WHY THIS IS NOT
REDUNDANT. Three test files embed the long form, but each pins the OUTPUT of the
one producer it exercises. None compares the producers to EACH OTHER, so a
lone-site edit leaves a three-way disagreement that no existing assertion can
observe. Most other fixtures use a SHORTER variant of the comment, which no
divergence here would disturb at all.

WHY SUBSTRING AND NOT AST. The three sites have three different SHAPES: a named
assignment, a bare literal inside an implicit concatenation, and a line inside a
triple-quoted template. No single AST query reaches all three. The comparison is
made on source text with implicit concatenation collapsed first -- a phrase split
across adjacent literals is not a contiguous substring of the source, so the
collapse is load-bearing rather than cosmetic.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

_SSOT = _PLUGIN_ROOT / "skills" / "pact-memory" / "scripts" / "working_memory.py"
_MIRRORS = (
    _PLUGIN_ROOT / "hooks" / "shared" / "session_resume.py",
    _PLUGIN_ROOT / "hooks" / "shared" / "claude_md_manager.py",
)

# Both managed-section comments are mirrored, not just the working-memory one.
_MIRRORED_CONSTANTS = ("WORKING_MEMORY_COMMENT", "RETRIEVED_CONTEXT_COMMENT")


def _collapse_implicit_concatenation(text: str) -> str:
    """Join adjacent string literals so a split phrase becomes contiguous."""
    return re.sub(r'"\s*\n\s*"', "", text)


def _ssot_constant(name: str) -> str:
    """Read a module-level string constant out of the SSOT by AST."""
    tree = ast.parse(_SSOT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if getattr(target, "id", None) == name:
                    return node.value.value
    raise AssertionError(
        f"{name} is not a module-level string constant in {_SSOT}. It was "
        f"renamed or restructured -- re-point this test, do not delete it."
    )


class TestTheInstrumentReachesItsPopulation:
    """Controls. A mirror check that read nothing would pass vacuously."""

    def test_every_file_exists_and_is_non_empty(self):
        for path in (_SSOT, *_MIRRORS):
            assert path.is_file(), f"missing: {path}"
            assert path.read_text(encoding="utf-8").strip(), f"empty: {path}"

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    def test_the_ssot_constant_is_readable_and_non_empty(self, name):
        value = _ssot_constant(name)
        assert value.strip(), f"{name} resolved to an empty string"


class TestTheManagedCommentsAgreeAcrossEveryWriter:
    """The invariant the prose instruction only asked for."""

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    @pytest.mark.parametrize("mirror", _MIRRORS, ids=lambda p: p.name)
    def test_mirror_carries_the_ssot_text(self, name, mirror):
        expected = _ssot_constant(name)
        source = _collapse_implicit_concatenation(
            mirror.read_text(encoding="utf-8")
        )
        assert expected in source, (
            f"{mirror.name} no longer carries the {name} text that "
            f"{_SSOT.name} defines. The three writers now disagree, so a "
            f"CLAUDE.md gets a different comment depending on which one last "
            f"touched it. Change all three together.\n"
            f"  expected: {expected!r}"
        )


class TestThisGuardCanFire:
    """Mutation arm. Without it the assertions above could pass against a
    comparison that cannot fail -- which is the exact defect class this test
    exists to close, one level up.

    READ THIS BEFORE YOU TREAT THIS ARM AS COVERAGE OF THE FAMILY. It mutates
    the SSOT CONSTANT and asserts the mutation is ABSENT from the mirror, so it
    is A CONTROL ON THE COMPARISON AND NOT ON THE EMISSION. It proves the
    comparison CAN fail. It says NOTHING about whether the comparison is on the
    RIGHT SUBJECT. A POSITIVE CONTROL VALIDATES THE PIPELINE AND NOT THE
    PATTERN.

    That distinction is the one this arm has been read against. A green here
    means the instrument is live. It does not mean an emitter still emits, and
    the behavioural sibling is what answers that question."""

    @pytest.mark.parametrize("mirror", _MIRRORS, ids=lambda p: p.name)
    def test_a_diverged_string_is_not_found(self, mirror):
        mutated = _ssot_constant("WORKING_MEMORY_COMMENT").replace(
            "Full history", "Partial history"
        )
        source = _collapse_implicit_concatenation(
            mirror.read_text(encoding="utf-8")
        )
        assert mutated not in source, (
            "the mutated string was found, so this comparison cannot "
            "distinguish agreement from disagreement"
        )
