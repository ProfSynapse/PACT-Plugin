"""Structural pin for the HANDOFF prose-label / canonical-key annotation.

The four LLM-loaded surfaces that teach the six-item HANDOFF template carry an
annotation, above the fence, naming the canonical `metadata.handoff` keys that
correspond to the prose display labels:

  1. pact-plugin/protocols/pact-phase-transitions.md
  2. pact-plugin/protocols/pact-protocols.md (SSOT mirror of the above)
  3. pact-plugin/commands/rePACT.md
  4. pact-plugin/skills/pact-agent-teams/SKILL.md

WHY THIS PIN EXISTS, AND WHY THE EXISTING GATE DOES NOT COVER IT.
verify-protocol-extracts.sh checks that the extract and the SSOT AGREE WITH
EACH OTHER. It does not check that either one SAYS anything in particular, so
it stays green when the annotation is deleted from BOTH protocol files in the
same commit. pact-phase-transitions.md is named by no other test file. So
before this pin, deleting the annotation from any of the four surfaces was
silent, and the one gate that looks like coverage was checking a different
property. This pin asserts CONTAINMENT AT EACH NAMED SURFACE, never agreement
between files.

TWO MARKERS, PINNED AS LITERALS, AND THAT IS DELIBERATE. Both are restated
here rather than imported. Building the expected value from
HANDOFF_CANONICAL_FIELDS would make this pin green whenever the docs and the
code drift TOGETHER, which is the failure a doc pin exists to catch. The one
arm that DOES import is test_doc_key_sequence_matches_shipped_canonical_fields
below, because it asserts doc-against-code and must read the code's actual
value. The two kinds of arm obey opposite rules on the same literal:

  - the literal pins catch the DOCS changing
  - the imported arm catches the docs and the code DIVERGING

A change made to both together passes the imported arm and fails the literal
pins. That is correct: it is a deliberate contract change and it should
require a test edit.

PER-FILE COUNTS, NOT A REPO-WIDE TOTAL. A repo-wide count stays green when a
phrase MOVES from one file to another, which is exactly the erosion this pin
is for.

POPULATION, STATED BESIDE THE CLAIM. These four are the ANNOTATED surfaces.
They are not every surface naming the six keys: agents/pact-orchestrator.md
also names all six, in canonical order, in a pre-existing sentence that gives
them directly as JSON keys. That sentence carries no prose display labels
beside them, so there is no label-to-key trap there and nothing to annotate.
It is why ANNOTATION_MARKER, not CANONICAL_KEY_SEQUENCE, is the marker that
identifies the annotation: the key sequence occurs on five surfaces, the
annotation phrase on exactly these four.

Counter-test-by-revert (manual): delete the annotation paragraph from any one
surface and this module reds with that surface named -- by the presence arm,
the drift arm and the count arm for that file.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared.handoff_schema import HANDOFF_CANONICAL_FIELDS  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Identifies the ANNOTATION itself. Present in both wordings the surfaces use
# ("These are PROSE labels." / "Those are PROSE labels;"), and nowhere else in
# the tree. Verbatim literal -- do not build this from a constant.
ANNOTATION_MARKER = "PROSE labels"

# The six canonical keys in canonical order, as the annotation names them.
# Backtick-stripped form: the surfaces render each key in backticks and
# _marker_text() normalizes that away, mirroring the repo's other phrase pins.
# Verbatim literal -- do not build this from HANDOFF_CANONICAL_FIELDS.
CANONICAL_KEY_SEQUENCE = (
    "produced, decisions, reasoning_chain, uncertainty, integration, open_questions"
)

DOC_SURFACES = [
    PLUGIN_ROOT / "protocols" / "pact-phase-transitions.md",
    PLUGIN_ROOT / "protocols" / "pact-protocols.md",
    PLUGIN_ROOT / "commands" / "rePACT.md",
    PLUGIN_ROOT / "skills" / "pact-agent-teams" / "SKILL.md",
]

# Per-surface expected occurrence count, for BOTH markers. One annotation per
# surface, each naming the key sequence once. Update in lockstep with any
# intentional change -- the brittleness IS the point. If the two markers ever
# need different counts on some surface, split this into one map per marker.
EXPECTED_COUNTS = {
    PLUGIN_ROOT / "protocols" / "pact-phase-transitions.md": 1,
    PLUGIN_ROOT / "protocols" / "pact-protocols.md": 1,
    PLUGIN_ROOT / "commands" / "rePACT.md": 1,
    PLUGIN_ROOT / "skills" / "pact-agent-teams" / "SKILL.md": 1,
}

MARKERS = [ANNOTATION_MARKER, CANONICAL_KEY_SEQUENCE]


def _marker_text(path: Path) -> str:
    """Read a doc surface with backticks stripped.

    The markers pin the PHRASE contract (words, not rendering). The repo's
    instruction-prose convention backticks tool and key names, so normalize
    rendering before matching -- same treatment as the other phrase pins.
    """
    return path.read_text(encoding="utf-8").replace("`", "")


def _fence_state(lines: list[str]) -> list[bool]:
    """True for each line that sits INSIDE a fenced code block.

    Takes RAW lines, never _marker_text() output. Backtick stripping erases
    the fence delimiters themselves, so a fence scan over normalized text
    finds no fences at all and reports every line as outside one. Measured:
    the first version of the fence arm read normalized text and stayed GREEN
    with the annotation moved inside the fence -- a dead arm that read as a
    passing one.
    """
    state, inside = [], False
    for line in lines:
        state.append(inside)
        if line.lstrip().startswith("```"):
            inside = not inside
    return state


@pytest.mark.parametrize("marker", MARKERS, ids=["annotation", "key_sequence"])
@pytest.mark.parametrize("doc_path", DOC_SURFACES, ids=lambda p: p.name)
def test_marker_present_in_doc_surface(doc_path: Path, marker: str):
    """Each annotated surface carries the annotation, naming all six keys.

    Two distinct failure modes, one arm each. The annotation marker catches
    the paragraph being deleted outright. The key sequence catches the
    paragraph surviving while a key is dropped, renamed, or reordered inside
    it -- which leaves the annotation marker green.
    """
    assert doc_path.exists(), (
        f"Doc surface missing on disk: {doc_path}. The HANDOFF key annotation "
        f"must be discoverable at all {len(DOC_SURFACES)} annotated surfaces."
    )
    assert marker in _marker_text(doc_path), (
        f"Marker {marker!r} missing from {doc_path.name}. An agent reading "
        f"this surface meets the six prose display labels with nothing telling "
        f"it the canonical metadata.handoff keys differ from them, which is "
        f"the label-copied-as-a-key trap this annotation exists to close. If "
        f"the wording changed intentionally, update the literal in this file "
        f"in lockstep."
    )


def test_annotation_consistent_across_all_surfaces():
    """Cross-surface drift: name every surface missing the annotation in ONE
    message, rather than as a list of separate parametrize failures.

    The expected failure shape is a change that updates 3 of the 4 surfaces --
    the two protocol files plus one other, forgetting the last. The
    parametrized arm reports that as an isolated red; this arm reports it as
    drift and names which surfaces fell behind.
    """
    missing = [
        doc.name for doc in DOC_SURFACES
        if ANNOTATION_MARKER not in _marker_text(doc)
    ]
    assert not missing, (
        f"Annotation marker {ANNOTATION_MARKER!r} missing from {len(missing)} "
        f"of {len(DOC_SURFACES)} annotated surfaces: {missing}. Cross-surface "
        f"drift -- the label-to-key mapping must be discoverable at every "
        f"surface that teaches the prose template, because an agent loads one "
        f"of them, not all four."
    )


@pytest.mark.parametrize("marker", MARKERS, ids=["annotation", "key_sequence"])
@pytest.mark.parametrize("doc_path", DOC_SURFACES, ids=lambda p: p.name)
def test_marker_count_per_surface(doc_path: Path, marker: str):
    """Pin the EXACT per-surface occurrence count.

    Per-file rather than repo-wide: a repo-wide total stays green when a
    phrase moves from one file to another, so it cannot see a surface losing
    its annotation while another gains a second copy.
    """
    expected = EXPECTED_COUNTS[doc_path]
    actual = _marker_text(doc_path).count(marker)
    assert actual == expected, (
        f"{doc_path.name}: marker {marker!r} appears {actual} time(s); "
        f"expected exactly {expected}. If this change is intentional (a "
        f"deliberate second annotation, or a consolidation), update "
        f"EXPECTED_COUNTS in lockstep. Otherwise the annotation has eroded on "
        f"this surface."
    )


@pytest.mark.parametrize("doc_path", DOC_SURFACES, ids=lambda p: p.name)
def test_annotation_sits_outside_the_fence(doc_path: Path):
    """The annotation must sit OUTSIDE the fenced template block.

    The fence is the COPY boundary: agents copy the fenced text into their
    prose response, so anything placed inside it is copied into every agent's
    HANDOFF forever, and an inline placement additionally defeats both
    lossless-field detectors in validate_handoff.py. Placement is therefore
    load-bearing, and every presence arm above stays GREEN if the annotation
    is moved inside the fence -- this is the only arm that would catch it.
    """
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    state = _fence_state(lines)
    inside = [
        i + 1 for i, line in enumerate(lines)
        if ANNOTATION_MARKER in line and state[i]
    ]
    assert not inside, (
        f"{doc_path.name}: the HANDOFF key annotation is inside a fenced "
        f"block at line(s) {inside}. The fence is the copy boundary -- an "
        f"annotation inside it lands in every agent's copied HANDOFF prose "
        f"and defeats the lossless-field detectors. Move it above the fence."
    )


def test_doc_key_sequence_matches_shipped_canonical_fields():
    """Doc-against-code: the sequence the surfaces teach IS the shipped
    canonical field order.

    This is the one arm that IMPORTS rather than restating, because it is a
    stand-in for the shipped schema: asserting against a remembered value
    would compare the docs to this file's author rather than to the code.
    Together with the literal arms above it closes the loop -- the literals
    pin what the docs say, this pins that what they say is what the code
    implements.

    IF THIS ARM REDS, THE DIVERGENCE IS THE FINDING. Do not relax it to make
    it pass: either the docs teach a key set the validator does not enforce,
    or the validator enforces one the docs never taught, and both are defects
    that reach an agent at runtime.
    """
    assert ", ".join(HANDOFF_CANONICAL_FIELDS) == CANONICAL_KEY_SEQUENCE, (
        f"HANDOFF_CANONICAL_FIELDS is {HANDOFF_CANONICAL_FIELDS!r}, which "
        f"renders as {', '.join(HANDOFF_CANONICAL_FIELDS)!r}, but the four "
        f"annotated doc surfaces teach {CANONICAL_KEY_SEQUENCE!r}. The docs "
        f"and the shipped schema have diverged -- an agent following the docs "
        f"would write keys the validator does not expect, or vice versa."
    )
