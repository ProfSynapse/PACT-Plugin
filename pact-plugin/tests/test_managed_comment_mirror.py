"""
Location: pact-plugin/tests/test_managed_comment_mirror.py

Summary: Enforces that the two managed-section comment strings agree across the
modules that carry them. `working_memory.py` holds the named constants and is
the SSOT. `claude_md_manager.py` repeats the same text as module constants.
`session_resume.py` no longer repeats the text at all: it IMPORTS the two names
from `claude_md_manager.py`, and three arms hold it to that.

WHY `_MIRRORS` NAMES ONE FILE, AND DO NOT PUT `session_resume.py` BACK IN IT.
The substring check searches the RAW SOURCE of each mirror for the SSOT text.
`session_resume.py` has no such text to find, because the literal was replaced
by an imported name. Restoring it to the tuple gives a RED THAT DESCRIBES
NOTHING: the file is correct and the instrument is looking for a spelling the
correctness removed. `claude_md_manager.py` stays in the tuple because it is the
one file inside `hooks/` where a literal spelling continues to be available to
search for.

WHAT THAT COSTS AND WHAT IT DOES NOT. The tuple feeds three arms, so the shrink
from two files to one takes this file from nine collected tests to six: two from
the identity arm and ONE FROM THE MUTATION ARM. THAT IS NOT A COVERAGE
REGRESSION AND A READER SHOULD NOT READ THE DROP AS ONE. The ratio is unchanged,
one can-fire case for each remaining mirror where it was two for two. The
subject of the gate got smaller and its guard got smaller with it. What replaces
the retired case is not that arithmetic: it is the three import-direction arms
and the constant-identity arm below, each with its own permanent can-fire case.

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
- hooks/shared/session_resume.py: the IMPORTER. It carries neither literal and
  takes both names from the hooks-side origin.
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

# THE HOOKS-SIDE ORIGIN. It is a MIRROR of the SSOT and, inside `hooks/`, the
# one file that spells the two comments. It is NOT an SSOT: that word names
# `_SSOT` above and nothing else in this family.
_HOOKS_ORIGIN = _PLUGIN_ROOT / "hooks" / "shared" / "claude_md_manager.py"

# The file that IMPORTS the two names rather than spelling them.
_IMPORTER = _PLUGIN_ROOT / "hooks" / "shared" / "session_resume.py"
_ORIGIN_MODULE = "shared.claude_md_manager"

# ONE ENTRY, and the file docstring says why putting the importer back is wrong.
_MIRRORS = (_HOOKS_ORIGIN,)

# Both managed-section comments are mirrored, not just the working-memory one.
_MIRRORED_CONSTANTS = ("WORKING_MEMORY_COMMENT", "RETRIEVED_CONTEXT_COMMENT")


def _collapse_implicit_concatenation(text: str) -> str:
    """Join adjacent string literals so a split phrase becomes contiguous."""
    return re.sub(r'"\s*\n\s*"', "", text)


def _imported_names(source: str, module: str) -> set[str]:
    """Names an `ImportFrom` brings in from `module`, read by AST.

    AST rather than a text search, because the question is which names the
    module BINDS, and a text search cannot separate a binding from a mention
    in a comment.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _module_level_bindings(source: str) -> set[str]:
    """Names bound by a MODULE-LEVEL assignment, read by AST.

    Module level only. A name assigned inside a function is a local and does
    not shadow the imported constant for the emitter.
    """
    bound: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            bound.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
    return bound


def _constant_in_source(source: str, name: str, where: str) -> str:
    """Read a module-level string constant out of `source` by AST."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if getattr(target, "id", None) == name:
                    return node.value.value
    raise AssertionError(
        f"{name} is not a module-level string constant in {where}. It was "
        f"renamed or restructured -- re-point this test, do not delete it."
    )


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


class TestTheImporterTakesTheCommentsFromTheOrigin:
    """Replaces the source-text presence question for `session_resume.py`.

    That file no longer spells the comments, so asking if its source carries
    the text is the wrong question. THE RIGHT QUESTION IS WHERE ITS NAMES COME
    FROM, and it has three parts: the import brings both names in, nothing
    rebinds them, and no literal was quietly re-added beside the import.
    """

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    def test_the_importer_binds_the_name_from_the_origin(self, name):
        names = _imported_names(_IMPORTER.read_text(encoding="utf-8"), _ORIGIN_MODULE)
        assert name in names, (
            f"{_IMPORTER.name} does not import {name} from {_ORIGIN_MODULE}. "
            f"Its creation template interpolates that name, so without the "
            f"import the module raises at import time rather than emitting a "
            f"different comment.\n  imported: {sorted(names)}"
        )

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    def test_the_importer_does_not_rebind_the_name(self, name):
        bound = _module_level_bindings(_IMPORTER.read_text(encoding="utf-8"))
        assert name not in bound, (
            f"{_IMPORTER.name} assigns {name} at module level, which shadows "
            f"the imported constant. The import then proves nothing about what "
            f"the emitter interpolates."
        )

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    def test_the_importer_does_not_respell_the_comment(self, name):
        expected = _ssot_constant(name)
        source = _collapse_implicit_concatenation(
            _IMPORTER.read_text(encoding="utf-8")
        )
        assert expected not in source, (
            f"{_IMPORTER.name} spells the {name} text again. That is the twin "
            f"this collapse removed, and a second spelling drifts in silence "
            f"because nothing compares it to the origin."
        )


class TestTheOriginAgreesWithTheSsot:
    """The identity question, asked between VALUES rather than between files.

    The substring arm asks if the origin's source CONTAINS the SSOT text. This
    asks if the origin's CONSTANT EQUALS it. The two differ when the origin
    holds the text in a comment and a different value in the constant, which
    the substring arm passes and this one does not.
    """

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    def test_the_origin_constant_equals_the_ssot_constant(self, name):
        origin = _constant_in_source(
            _HOOKS_ORIGIN.read_text(encoding="utf-8"), name, _HOOKS_ORIGIN.name
        )
        assert origin == _ssot_constant(name), (
            f"{_HOOKS_ORIGIN.name} defines {name} with a different value from "
            f"{_SSOT.name}. Everything inside hooks/ takes the name from that "
            f"file, so the whole hooks side now disagrees with the SSOT.\n"
            f"  origin: {origin!r}\n  ssot:   {_ssot_constant(name)!r}"
        )


class TestTheseArmsCanFire:
    """PERMANENT can-fire guards for the four arms above.

    RED-BEFORE-GREEN AND A PERMANENT CAN-FIRE ARM ARE DIFFERENT INSTRUMENTS.
    The first is a ONE-TIME proof by an author, recorded where no later run
    reads it. This RE-PROVES ON EVERY RUN.

    MEASURED, BY FEEDING EACH HELPER AN EMPTY MODULE. Of the four arms above,
    TWO FAIL CLOSED AND TWO CAN PASS VACUOUSLY.

      - binding arm:  FAILS CLOSED. An empty parse yields an empty name set,
                      and a presence assertion over an empty set is red.
      - identity arm: FAILS CLOSED, and for a different cause: the helper it
                      calls RAISES when the constant is absent, so an empty
                      source cannot return a value to compare.
      - rebind arm:   PASSES VACUOUSLY. An absence over an empty parse is
                      satisfied for the wrong cause.
      - respell arm:  PASSES VACUOUSLY. Same shape, over an empty read.

    THE TWO THAT FAIL CLOSED KEEP THEIR GUARDS ANYWAY, because fail-closed is a
    property of today's helper and not of the assertion, and a later helper that
    returns a default rather than raising would move the identity arm into the
    other column with nothing going red. Each guard feeds a PERTURBED SOURCE
    STRING to the same helper and asserts the arm's predicate flips.
    """

    def test_a_missing_import_is_caught(self):
        source = _IMPORTER.read_text(encoding="utf-8").replace(
            "    RETRIEVED_CONTEXT_COMMENT,\n", "", 1
        )
        names = _imported_names(source, _ORIGIN_MODULE)
        assert "RETRIEVED_CONTEXT_COMMENT" not in names, (
            "the binding arm cannot tell a present import from an absent one"
        )

    def test_a_module_level_rebind_is_caught(self):
        source = (
            _IMPORTER.read_text(encoding="utf-8")
            + '\nRETRIEVED_CONTEXT_COMMENT = "<!-- drifted -->"\n'
        )
        bound = _module_level_bindings(source)
        assert "RETRIEVED_CONTEXT_COMMENT" in bound, (
            "the rebind arm cannot see a module-level assignment, so its "
            "absence result says nothing"
        )

    def test_a_respelled_literal_is_caught(self):
        expected = _ssot_constant("WORKING_MEMORY_COMMENT")
        source = _collapse_implicit_concatenation(
            _IMPORTER.read_text(encoding="utf-8") + f'\n_X = "{expected}"\n'
        )
        assert expected in source, (
            "the respell arm cannot find a re-added literal, so its absence "
            "result says nothing"
        )

    @pytest.mark.parametrize("name", _MIRRORED_CONSTANTS)
    def test_a_diverged_origin_constant_is_caught(self, name):
        expected = _ssot_constant(name)
        source = _HOOKS_ORIGIN.read_text(encoding="utf-8").replace(
            f'{name} = "{expected}"', f'{name} = "<!-- drifted -->"', 1
        )
        origin = _constant_in_source(source, name, _HOOKS_ORIGIN.name)
        assert origin != expected, (
            f"the identity arm read {origin!r} from a source whose {name} was "
            f"perturbed, so the comparison cannot separate agreement from "
            f"disagreement"
        )
