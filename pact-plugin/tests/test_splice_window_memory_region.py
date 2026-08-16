"""The two write-side splice windows are bound to the MEMORY region.

SIBLING OF `test_pin_marker_writer.py`, and it borrows that module's
production-derived builders rather than spell a boundary of its own.

WHAT THIS GUARDS. `extract_managed_region` returns the WIDE managed region.
The session block sits IN that region and ABOVE the memory marker pair, and
it interpolates caller-influenced values. The two write-side parsers search
their heading FIRST-MATCH in the window they get, and the offset of that
match rebuilds the file. So a forged `## Working Memory` line in the session
block takes the splice ABOVE the memory region, and the write lands outside
the part of the document the memory layer owns.

WHY THE ARMS ARE HERE AND NOT BESIDE THE SOURCE. The source is the work of
another seat. These arms are written from the DOCUMENT SHAPE rather than
from a read of that implementation, so they say what the writer must DO and
not how it is built.

THE RULE EACH ASSERTION BELOW OBEYS: IT MUST PASS AGAINST A DIFFERENT
CORRECT IMPLEMENTATION AND GO RED AGAINST THE WIDENING. So nothing here
asserts that a narrowing helper was called, what it returns, or the offsets
234, 274, 277, 304 and 377 that the author measured. Each of those is a fact
about one implementation, and each reddens on a clean refactor that keeps
the behaviour, which is a cost on a later author rather than a guard.

THE ORACLE IS INDEPENDENT OF THE MODULE UNDER TEST. The marker literals come
from `shared.claude_md_manager`, which is the canonical copy in the hooks
tree. A test that located the region with the constants of the module it
guards would agree with that module about the region by construction.

EACH ABSENCE ASSERTION HAS A POSITIVE PARTNER. Measured on this branch: an
absence assertion passed against leaking code, because an upstream
truncation removed the evidence rather than the defect. So where a test
below says the splice is NOT above the region, it also says where the splice
IS.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from shared.claude_md_manager import MEMORY_START_MARKER, MEMORY_END_MARKER
from tests.test_pin_marker_writer import build_claude_md

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts"))


# The text this suite looks for in the emitted document. It is deliberately
# distinctive, so `str.index` finds the entry and nothing else.
ENTRY_SENTINEL = "SpliceWindowSentinelZZ"


def _forge_heading_in_session_block(document: str, heading: str) -> str:
    """Put `heading` IN the managed region and ABOVE the memory start marker.

    THE POSITION IS COMPUTED FROM THE MARKER RATHER THAN FROM AN OFFSET. The
    document comes from the production emitter through `build_claude_md`, and
    production puts the managed marker, the title and the session block ABOVE
    the memory start marker. So the line immediately above that marker is in
    the session block, which is the place the forged heading has to sit for
    this to be the measured defect rather than a different one.
    """
    marker_at = document.index(MEMORY_START_MARKER)
    line_start = document.rfind("\n", 0, marker_at) + 1
    return document[:line_start] + heading + "\n\n" + document[line_start:]


def _write_and_sync(tmp_path, document, sync):
    """Write `document`, run `sync` against it, and return the emitted text."""
    target = tmp_path / "CLAUDE.md"
    target.write_text(document, encoding="utf-8")
    with patch(
        "working_memory._resolve_display_claude_md_with_base",
        return_value=(target, target.parent),
    ):
        sync()
    return target.read_text(encoding="utf-8")


def _assert_document_is_the_measured_shape(document, heading):
    """PRECONDITIONS, so a green below cannot come from a fixture that lost
    the decoy. Each one is a fact about the INPUT and not about the writer."""
    assert document.count(heading) == 2, (
        f"the fixture must carry {heading!r} TWICE, the forged one in the "
        f"session block and the genuine one in the memory region. Found "
        f"{document.count(heading)}. A one-heading fixture reproduces nothing."
    )
    start = document.index(MEMORY_START_MARKER)
    end = document.index(MEMORY_END_MARKER)
    assert document.index(heading) < start, (
        "the FORGED heading must sit above the memory start marker"
    )
    assert start < document.rindex(heading) < end, (
        "the GENUINE heading must sit in the memory region"
    )


class TestWorkingMemorySpliceWindow:
    """`## Working Memory` is written in the memory region, not above it."""

    HEADING = "## Working Memory"

    def _sync(self, tmp_path, document):
        from working_memory import sync_to_claude_md

        return _write_and_sync(
            tmp_path,
            document,
            lambda: sync_to_claude_md(
                {"context": ENTRY_SENTINEL}, memory_id="0123456789abcdef" * 2
            ),
        )

    def test_the_entry_lands_in_the_memory_region(self, tmp_path):
        """POSITIVE: the new entry sits between the two memory markers.

        THIS IS THE ARM THE BOUND EXISTS FOR. With the window widened to the
        managed region, the parser matches the FORGED heading first, and the
        entry is written above the memory region.
        """
        document = _forge_heading_in_session_block(build_claude_md(), self.HEADING)
        _assert_document_is_the_measured_shape(document, self.HEADING)

        emitted = self._sync(tmp_path, document)

        # NON-VACUITY: the sync must have run and written the entry.
        assert ENTRY_SENTINEL in emitted, (
            "the sync did not write the entry, so this arm tested nothing"
        )
        start = emitted.index(MEMORY_START_MARKER)
        end = emitted.index(MEMORY_END_MARKER)
        at = emitted.index(ENTRY_SENTINEL)
        assert start < at < end, (
            f"the entry landed at {at} against a memory region of "
            f"[{start}, {end}]. A write outside that region puts memory "
            f"content in the part of the document the memory layer does not own."
        )

    def test_the_text_above_the_memory_region_is_unchanged(self, tmp_path):
        """ABSENCE, PAIRED WITH THE POSITIVE ARM ABOVE.

        Alone this passes when the writer removes the region rather than
        respects it, so it is written as a byte comparison of the prefix AND
        the companion arm above asserts where the entry went.
        """
        document = _forge_heading_in_session_block(build_claude_md(), self.HEADING)
        _assert_document_is_the_measured_shape(document, self.HEADING)
        prefix_before = document[: document.index(MEMORY_START_MARKER)]

        emitted = self._sync(tmp_path, document)

        # NON-VACUITY: an emitted document with no marker would make the
        # comparison below trivially true on an empty slice.
        assert MEMORY_START_MARKER in emitted
        assert ENTRY_SENTINEL in emitted
        prefix_after = emitted[: emitted.index(MEMORY_START_MARKER)]
        assert prefix_after == prefix_before, (
            "the text above the memory start marker changed. The session "
            "block and the user prose above it are not the memory layer's "
            "to rewrite."
        )


class TestRetrievedContextSpliceWindow:
    """`## Retrieved Context` is written in the memory region, not above it."""

    HEADING = "## Retrieved Context"

    def _sync(self, tmp_path, document):
        from working_memory import sync_retrieved_to_claude_md

        return _write_and_sync(
            tmp_path,
            document,
            lambda: sync_retrieved_to_claude_md(
                [{"context": ENTRY_SENTINEL}],
                query="q",
                memory_ids=["0123456789abcdef" * 2],
            ),
        )

    def test_the_entry_lands_in_the_memory_region(self, tmp_path):
        """POSITIVE: the retrieved entry sits between the two memory markers."""
        document = _forge_heading_in_session_block(build_claude_md(), self.HEADING)
        _assert_document_is_the_measured_shape(document, self.HEADING)

        emitted = self._sync(tmp_path, document)

        assert ENTRY_SENTINEL in emitted, (
            "the sync did not write the entry, so this arm tested nothing"
        )
        start = emitted.index(MEMORY_START_MARKER)
        end = emitted.index(MEMORY_END_MARKER)
        at = emitted.index(ENTRY_SENTINEL)
        assert start < at < end, (
            f"the entry landed at {at} against a memory region of "
            f"[{start}, {end}]."
        )

    def test_the_text_above_the_memory_region_is_unchanged(self, tmp_path):
        """ABSENCE, PAIRED WITH THE POSITIVE ARM ABOVE."""
        document = _forge_heading_in_session_block(build_claude_md(), self.HEADING)
        _assert_document_is_the_measured_shape(document, self.HEADING)
        prefix_before = document[: document.index(MEMORY_START_MARKER)]

        emitted = self._sync(tmp_path, document)

        assert MEMORY_START_MARKER in emitted
        assert ENTRY_SENTINEL in emitted
        prefix_after = emitted[: emitted.index(MEMORY_START_MARKER)]
        assert prefix_after == prefix_before, (
            "the text above the memory start marker changed."
        )


class TestMissingPairKeepsTodayBehaviour:
    """A managed document with NO memory pair keeps the wide window.

    THIS ARM PINS WHAT THE CODE DOES TODAY, and today's behaviour predates
    the bound on purpose. It is named so a later author can find it and
    re-point it rather than delete it.

    THE TRIGGER IS THE CODE AND NOT A RULING, AND THE DIFFERENCE IS NOT
    PEDANTIC. An earlier version of this docstring said to re-point WHEN THE
    RULING LANDS. THE RULING HAS LANDED AND THE IMPLEMENTATION HAS NOT, so
    that trigger reads as satisfied against code that has not moved, and a
    reader who obeys it re-points a correct arm at a behaviour the writer
    does not have. A test instruction keyed on a DECISION goes stale at the
    decision. One keyed on an EXPRESSION goes stale at the expression, which
    is the thing the arm measures.

    SO RE-POINT THIS ARM WHEN, AND ONLY WHEN, THE TWO CONDITIONS BELOW STOP
    HOLDING IN `skills/pact-memory/scripts/working_memory.py`:

      1. `_narrow_to_memory_region` returns None when the memory marker pair
         is missing.
      2. The two callers of it fall back to the WIDE managed region, each
         through `narrowed if narrowed is not None else region_result`.

    While the two hold, the write goes ahead and this arm is correct. When
    either one moves, the class this arm covers (a managed document with no
    memory pair) keeps its behaviour either way, and only the expected
    direction moves. DO NOT REMOVE THE ARM.
    """

    def test_a_document_with_no_memory_pair_is_written_without_raising(
        self, tmp_path
    ):
        from working_memory import sync_to_claude_md

        document = build_claude_md(managed=False)
        # PRECONDITION: this class covers a document with NO memory pair.
        assert MEMORY_START_MARKER not in document
        assert MEMORY_END_MARKER not in document

        emitted = _write_and_sync(
            tmp_path,
            document,
            lambda: sync_to_claude_md({"context": ENTRY_SENTINEL}),
        )

        assert ENTRY_SENTINEL in emitted, (
            "today's behaviour writes the entry for this class, and it did "
            "not.\n"
            "RE-POINT THIS ARM AT THE NEW EXPRESSION RATHER THAN REMOVE IT, "
            "and read the class docstring first: the trigger is the CODE in "
            "`working_memory.py`, not a ruling. A ruling on this direction "
            "can land months before the expression moves, so a decision is "
            "the wrong thing to key a test instruction on."
        )
