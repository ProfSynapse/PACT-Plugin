"""The session-end marker survives a forged section heading above it.

WHAT THIS GUARDS. The section-end scanners search their heading FIRST-MATCH in
the window they are given. When the memory marker pair is missing, that window
falls back to the WIDE managed region, and the session block sits in it. A
forged section heading in the session block then wins the search, and the body
scan runs from that heading. If the scan does not stop at `<!-- SESSION_END -->`
the rebuild replaces the span that holds it, and the marker is GONE from the
emitted document. `CLAUDE.md` is not a tracked file here, so no commit restores
it.

WHY THIS FILE EXISTS AT ALL. The source repair shipped with its author
recording that a green suite proved nothing about it, and that the evidence
lived in a probe the author deleted. This file is that evidence, made
permanent.

=====================================================================
THE SEPARATION MATRIX, MEASURED, AND IT DECIDES THE ARM COUNT
=====================================================================

The repair touches FOUR regex sites: a LOOKAHEAD site and a TERMINATOR site in
each of the two section parsers. Each site was reverted INDEPENDENTLY, scoped
by the ast line range of its function, against four candidate fixtures. `X`
marks a document that lost its session-end marker.

    reverted site        WM-look  WM-term  RC-look  RC-term
    WM lookahead            X        .        .        .
    WM terminator           X        X        .        .
    RC lookahead            .        .        X        .
    RC terminator           .        .        X        X

READ IT BY COLUMN. The WM-look fixture catches the two WORKING MEMORY reverts
and NO Retrieved Context revert. The RC-look fixture catches the two RETRIEVED
CONTEXT reverts and no Working Memory revert. The two terminator fixtures each
catch a strict subset of what their own lookahead fixture catches, so they add
no kill.

SO THE MINIMAL SUFFICIENT SET IS TWO ARMS, AND THE AXIS IS THE SECTION AND NOT
THE HALF. Each arm below is NECESSARY: neither one catches a single revert in
the other section. A terminator-shape arm is not necessary, because the
lookahead shape reaches both halves of its own section.

THE LOOKAHEAD SHAPE REACHES BOTH HALVES FOR ONE CAUSE. With the heading on the
line above the marker, the marker is the candidate the optional auto-managed
comment group would consume, AND it is the first boundary the body scan meets.
Either site alone is enough to swallow it, so the fixture that puts it in both
positions catches either revert.

=====================================================================
THE FIXTURE RULES, AND EACH ONE ANSWERS A MEASURED FAILURE
=====================================================================

1. THE BOUNDARY COMES FROM THE PRODUCTION EMITTER, through `build_claude_md`
   and `production_head_and_tail`, and never from a literal here. A
   hand-written boundary agrees with every other hand-written boundary and
   with nothing that ships.

2. THE FORGED HEADING TEXT APPEARS TWICE. With one heading the defect run and
   a correct run emit the same document, so the run separates nothing. The
   count is PRINTED beside each arm, so the control is visible rather than
   asserted.

3. THE MEMORY MARKER PAIR IS ABSENT. Measured: with the pair PRESENT the
   window bound keeps the write inside the memory region and the marker
   survives every one of the four reverts. The erasure needs the pair-absent
   fallback, so an arm built on a pair-present document is green against the
   defect it is named for.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from shared.claude_md_manager import MEMORY_START_MARKER, MEMORY_END_MARKER
from tests.test_pin_marker_writer import build_claude_md

sys.path.insert(
    0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts")
)

SESSION_END = "<!-- SESSION_END -->"

# Distinctive, so `str.index` finds the written entry and nothing else.
ENTRY_SENTINEL = "SessionEndArmSentinelZZ"


def _without_the_memory_pair(document: str) -> str:
    """Remove the two memory marker LINES and change nothing else.

    ONE AXIS FLIPPED against a production-derived document. The managed region
    stays, the session block stays, the section bodies stay.
    """
    return "".join(
        line
        for line in document.splitlines(keepends=True)
        if line.strip() not in (MEMORY_START_MARKER, MEMORY_END_MARKER)
    )


def _forge_above_the_session_end(document: str, heading: str) -> str:
    """Put `heading` on its own line IMMEDIATELY ABOVE the session-end marker.

    THE POSITION IS COMPUTED FROM THE MARKER RATHER THAN FROM AN OFFSET, and
    it is the lookahead shape from the matrix in the module docstring: the
    marker sits where the optional auto-managed comment would be consumed AND
    where the body scan first meets a boundary.
    """
    marker_at = document.index(SESSION_END)
    line_start = document.rfind("\n", 0, marker_at) + 1
    return document[:line_start] + heading + "\n" + document[line_start:]


def _build(heading: str) -> str:
    return _forge_above_the_session_end(
        _without_the_memory_pair(build_claude_md()), heading
    )


def _assert_the_document_is_the_measured_shape(document: str, heading: str) -> int:
    """PRECONDITIONS, so a green cannot come from a fixture that lost its decoy.

    Returns the heading count, which each arm PRINTS. Each assertion here is a
    fact about the INPUT and not about the writer.
    """
    count = document.count(heading)
    assert count == 2, (
        f"the fixture must carry {heading!r} TWICE, the forged one in the "
        f"session block and the genuine one below. Found {count}. With one "
        "heading the defect run and a correct run emit the SAME document, so "
        "the run separates nothing."
    )
    assert MEMORY_START_MARKER not in document, (
        "the memory START marker must be absent. With the pair present the "
        "window bound keeps the write inside the memory region and the marker "
        "survives every revert, so the arm would be green against its defect."
    )
    assert MEMORY_END_MARKER not in document, (
        "the memory END marker must be absent, for the same cause."
    )
    assert SESSION_END in document, "the fixture lost the marker under test"
    assert document.index(heading) < document.index(SESSION_END), (
        "the FORGED heading must sit ABOVE the session-end marker"
    )
    return count


def _write_and_sync(tmp_path, document, call):
    target = tmp_path / "CLAUDE.md"
    target.write_text(document, encoding="utf-8")
    with patch(
        "working_memory._resolve_display_claude_md_with_base",
        return_value=(target, target.parent),
    ):
        call()
    return target.read_text(encoding="utf-8")


def _assert_the_marker_survived(emitted: str, heading: str, count_in: int, label: str):
    """The shared oracle. It is a PRESENCE check with two non-vacuity legs."""
    # NON-VACUITY LEG 1: the sync must have run and written its entry. An
    # emitted document that never changed passes a presence check for the
    # wrong cause.
    assert ENTRY_SENTINEL in emitted, (
        f"{label}: the sync wrote no entry, so this arm exercised nothing"
    )
    # NON-VACUITY LEG 2: print the control rather than assert it alone, so a
    # reader sees the heading population the run actually had.
    print(
        f"  {label}: headings in {count_in}, headings out "
        f"{emitted.count(heading)}, marker present: {SESSION_END in emitted}"
    )
    assert SESSION_END in emitted, (
        f"{label}: THE SESSION-END MARKER IS GONE FROM THE EMITTED DOCUMENT.\n"
        f"A body scanned from the forged {heading!r} in the session block ran "
        "THROUGH the marker line and the rebuild replaced the span that held "
        "it. The marker is a precondition of the window rule that protects "
        "this write, and CLAUDE.md is not tracked here, so no commit restores "
        "it.\n"
        "THE TWO SITES THAT REACH THIS, and a repair must cover the one that "
        "moved: the optional auto-managed comment LOOKAHEAD after the heading, "
        "and the section-end TERMINATOR alternation. Read the separation "
        "matrix in this module docstring before you narrow either one."
    )


class TestWorkingMemorySectionStopsAtTheSessionEnd:
    """The working-memory writer does not consume the session-end marker.

    THIS ARM CATCHES BOTH WORKING MEMORY REVERTS AND NEITHER RETRIEVED CONTEXT
    REVERT. It is necessary and it is not sufficient. Its partner below covers
    the other section.
    """

    HEADING = "## Working Memory"

    def test_the_marker_survives_a_forged_heading_in_the_session_block(
        self, tmp_path
    ):
        from working_memory import sync_to_claude_md

        document = _build(self.HEADING)
        count_in = _assert_the_document_is_the_measured_shape(document, self.HEADING)

        emitted = _write_and_sync(
            tmp_path,
            document,
            lambda: sync_to_claude_md({"context": ENTRY_SENTINEL}),
        )
        _assert_the_marker_survived(
            emitted, self.HEADING, count_in, "working memory"
        )


class TestRetrievedContextSectionStopsAtTheSessionEnd:
    """The retrieved-context writer does not consume the session-end marker.

    THIS ARM CATCHES BOTH RETRIEVED CONTEXT REVERTS AND NEITHER WORKING MEMORY
    REVERT. Measured, not assumed: the two parsers carry their own copies of
    the two regex sites, so a repair applied to one section leaves the other
    reverting in silence.
    """

    HEADING = "## Retrieved Context"

    def test_the_marker_survives_a_forged_heading_in_the_session_block(
        self, tmp_path
    ):
        from working_memory import sync_retrieved_to_claude_md

        document = _build(self.HEADING)
        count_in = _assert_the_document_is_the_measured_shape(document, self.HEADING)

        emitted = _write_and_sync(
            tmp_path,
            document,
            lambda: sync_retrieved_to_claude_md(
                [{"context": ENTRY_SENTINEL}],
                query="q",
                memory_ids=["0123456789abcdef" * 2],
            ),
        )
        _assert_the_marker_survived(
            emitted, self.HEADING, count_in, "retrieved context"
        )
