"""The memory-entry heading the writers emit, against the gate rule that reads it.

WHY THIS FILE SITS WITH THE WRITERS AND NOT WITH THE GATE. The failure guarded
here is a WRITER change that invalidates a precondition the GATE depends on.
The person who makes that change is editing `working_memory.py` and has no
reason to open the tests of `pin_staleness_gate.py`. An arm parked beside the
gate is invisible to the one person able to break it.

WHAT THE GATE DOES WITH THE HEADING. `pin_staleness_gate.py` excludes an entry
from the pin count when its heading is DATE-LED and it carries no
`<!-- pinned: -->` marker. That exclusion is what stops memory entries counting
as pins. If it stops accepting the emitted heading, the count rises, the gate
fires, and a faithful edit to the Pinned Context section is DENIED.

THE ARM HOLDS A RELATION, NOT A FORMAT, AND THAT IS THE WHOLE DESIGN.
A format pin makes a claim about ONE party: the writer. The property worth
holding is an AGREEMENT between two parties that live in different files. A
one-sided pin reddens when the WRITER moves and stays GREEN when the GATE
moves, so tightening the gate pattern breaks the pair with a passing arm over
it. That direction is worse than an abandoned arm, because the gate continues
to depend on the format and now disagrees with it, so nothing looks abandoned
and nothing reports.

SO THE VALUE COMES FROM THE WRITER AND THE PREDICATE COMES FROM THE GATE.
The arm calls the writer, takes the heading it ACTUALLY emits, imports
`_DATE_LED_HEADING_RE`, and asserts the pattern accepts that heading. THIS IS
NOT THE PATTERN TESTED AGAINST ITSELF: nothing here copies the pattern in as an
expected value, and the two sides come from two files. It reddens when either
end moves.

WHY NOT DESCRIBE THE SHAPE IN THIS FILE INSTEAD. The heading carries a
timestamp built at call time, so an arm cannot assert a literal and must
DESCRIBE the shape. That description becomes a THIRD spelling of the date
shape, beside the writer format string and the gate pattern. Three spellings
that must agree is the generator of the drift this arm is here to catch.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
sys.path.insert(
    0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts")
)

# The two writers that emit a memory-entry heading. Each is driven for real
# below; nothing here reconstructs what they emit.
_WRITERS = ("_format_memory_entry", "_format_retrieved_entry")


def _emit(writer_name: str) -> str:
    """Drive a writer and return the FIRST LINE of what it produced.

    The payload is deliberately minimal. The heading carries a timestamp and
    no payload field, so a richer payload changes the body and not the line
    under test.
    """
    import working_memory as wm

    payload = {"context": "context text", "goal": "goal text"}
    if writer_name == "_format_memory_entry":
        entry = wm._format_memory_entry(payload, None, "entry-under-test")
    else:
        entry = wm._format_retrieved_entry(payload, "a query", 0.9, "entry-under-test")
    return entry.splitlines()[0]


class TestTheGateAcceptsWhatTheWritersEmit:
    """The load-bearing arm, plus the two controls that make it evidence."""

    @pytest.mark.parametrize("writer", _WRITERS)
    def test_the_gate_accepts_the_heading_this_writer_emits(self, writer):
        """THE ARM. Writer supplies the value, gate supplies the predicate."""
        from pin_staleness_gate import _DATE_LED_HEADING_RE

        heading = _emit(writer)

        assert _DATE_LED_HEADING_RE.match(heading.strip()), (
            f"THE PIN STALENESS GATE NO LONGER RECOGNISES THIS HEADING.\n"
            f"  writer   : working_memory.{writer}\n"
            f"  emitted  : {heading!r}\n"
            f"  gate rule: _DATE_LED_HEADING_RE in hooks/pin_staleness_gate.py\n"
            f"\n"
            f"WHAT THAT RULE DOES. It excludes an entry from the pin count when "
            f"the heading is DATE-LED and the entry carries no "
            f"`<!-- pinned: -->` marker. That exclusion is the only thing that "
            f"stops memory entries counting as pins.\n"
            f"\n"
            f"THE CONSEQUENCE IF YOU LEAVE THIS RED. The exclusion stops "
            f"matching, memory entries count as pins again, the staleness gate "
            f"OVER-BLOCKS, and a faithful edit to the ## Pinned Context section "
            f"of CLAUDE.md is DENIED.\n"
            f"\n"
            f"DO NOT DELETE THIS ARM TO GO GREEN. Either restore the emitted "
            f"heading format, or update _DATE_LED_HEADING_RE in the SAME commit "
            f"and say so in the message."
        )

    @pytest.mark.parametrize("writer", _WRITERS)
    def test_the_writer_emitted_a_heading_at_all(self, writer):
        """CONTROL ONE, ON THE VALUE. A writer that returned an empty first
        line, or a body whose first line is not a heading, would make the arm
        above a statement about nothing. This proves the harness drove a writer
        that produced a heading."""
        heading = _emit(writer)

        assert heading.startswith("### "), (
            f"{writer} did not emit a heading as its first line: {heading!r}"
        )
        assert any(ch.isdigit() for ch in heading), (
            f"{writer} emitted a heading with no digit in it: {heading!r}. The "
            f"gate rule is about a DATE-LED heading, so a heading with no digit "
            f"means the arm above is testing the wrong line"
        )

    def test_the_gate_predicate_refuses_a_heading_that_is_not_date_led(self):
        """CONTROL TWO, ON THE PREDICATE, AND IT IS THE ONE THAT MATTERS.

        A pattern that accepted everything would satisfy the arm above forever,
        and it would satisfy it LOUDEST in the state this file exists to catch.
        The arm above is evidence only once the predicate is known to refuse
        something. This is that proof."""
        from pin_staleness_gate import _DATE_LED_HEADING_RE

        assert not _DATE_LED_HEADING_RE.match("### Some Curated Pin Title"), (
            "_DATE_LED_HEADING_RE accepts a heading that is NOT date-led, so it "
            "no longer separates a memory entry from a curated pin, and the "
            "acceptance arm above proves nothing"
        )


class TestTheOptionalTimeGroupIsUnexercised:
    """A MEASURED OBSERVATION, NOT A GUARD. Recorded so a later reader meets it.

    `_DATE_LED_HEADING_RE` makes the hour-and-minute group OPTIONAL, so it
    accepts a date-only heading. NEITHER WRITER EMITS ONE: each builds its
    heading from a format that carries a date AND a time. So the optional
    branch has no producer in the shipped tree.

    WHY THAT IS WORTH RECORDING. It is the surface where drift can happen
    unobserved. A writer that later emits a date-only heading would be accepted
    with no arm reporting the change of shape, and a later editor who removes
    the optional group would break nothing that runs today. This class states
    the position rather than defends it.
    """

    def test_the_pattern_accepts_a_date_only_heading(self):
        from pin_staleness_gate import _DATE_LED_HEADING_RE

        assert _DATE_LED_HEADING_RE.match("### 2026-08-12")

    @pytest.mark.parametrize("writer", _WRITERS)
    def test_no_writer_emits_a_date_only_heading(self, writer):
        heading = _emit(writer).strip()
        # Three whitespace-separated parts: the marker, the date, the time.
        assert len(heading.split()) == 3, (
            f"{writer} emitted {heading!r}, which is not the "
            f"marker-date-time shape this observation was recorded against. "
            f"Re-read the optional-group note in this class: its premise has "
            f"changed"
        )
