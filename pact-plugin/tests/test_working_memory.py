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

    @pytest.mark.parametrize(
        "title",
        [
            "### 2026-08-05 Draft notes",
            "### 2026-08-05 12:30 Draft notes",
            "### 2026-08-05  Merge guard purpose",
        ],
    )
    def test_the_gate_predicate_refuses_a_date_followed_by_a_title(self, title):
        """CONTROL THREE, ON THE DATE SIDE OF THE ALPHABET.

        WHY CONTROL TWO ABOVE IS NOT ENOUGH, AND THIS IS A GAP I LEFT MYSELF.
        Control two feeds a title with NO DATE in it, so it bounds the
        NON-DATE direction only. The exclusion cannot grow in that direction.
        IT CAN GROW IN THE DATE DIRECTION, and nothing bounded that. Peer
        review widened the trailing anchor of `_DATE_LED_HEADING_RE` so the
        pattern accepts a date FOLLOWED BY A TITLE, and 47 of 47 arms stayed
        green. The alphabet of a control must come from the GUARDED THING, and
        mine came from the case I expected to fail.

        THE WIDENED PATTERN HAS TWO FAILURE DIRECTIONS AND THE SECOND IS
        CARDINAL.
          1. QUIET. A true pin add titled with a date prefix stops counting as
             a pin, so the gate says nothing where it should speak. That is an
             under-block.
          2. DENY, AND THIS ONE IS THE CARDINAL DIRECTION. A user RENAMES a pin
             from `### 2026-08-05 Draft notes` to `### Draft notes`, with no
             marker on either side. The widened pattern drops the OLD title
             from the count, the old count falls, the new count is then the
             greater, and the gate FIRES where the shipped tree stayed quiet.
             A faithful rename is DENIED.

        AND THE WIDENED POPULATION SITS OUTSIDE THE USER RULING. The ruling
        declares empty the population of a pin titled a BARE date with no
        marker. `### 2026-08-05 Draft notes` is not a bare date, so the ruling
        does not cover the class the widening opens, while the shipped
        docstring of `_is_memory_entry` continues to assert that ruling.
        """
        from pin_staleness_gate import _DATE_LED_HEADING_RE

        assert not _DATE_LED_HEADING_RE.match(title), (
            f"_DATE_LED_HEADING_RE ACCEPTS {title!r}, A DATE FOLLOWED BY A "
            f"TITLE.\n"
            f"That is a CURATED PIN, not a memory entry, so the gate now "
            f"excludes it from the pin count.\n"
            f"  DIRECTION 1, quiet: a true pin add stops counting, and the "
            f"gate says nothing where it should speak.\n"
            f"  DIRECTION 2, deny, and this is the CARDINAL one: a user who "
            f"renames such a pin and drops the date loses a title from the OLD "
            f"count, so the new count becomes the greater and the gate FIRES. "
            f"A faithful rename is DENIED.\n"
            f"The trailing anchor of the pattern is what holds this. Do not "
            f"widen it. If the exclusion must grow, price the two directions "
            f"first, and note that the user ruling covers a BARE date only."
        )


class TestTheOptionalTimeGroupIsUnexercised:
    """A MEASURED OBSERVATION, NOT A GUARD. Recorded so a later reader meets it.

    `_DATE_LED_HEADING_RE` makes the hour-and-minute group OPTIONAL, so it
    accepts a date-only heading. NEITHER WRITER EMITS ONE: each builds its
    heading from a format that carries a date AND a time. So the optional
    branch has no producer in the shipped tree.

    WHY THAT IS WORTH RECORDING. It is the surface where drift can happen
    unobserved. A writer that later emits a date-only heading would be accepted
    with no arm reporting the change of shape. This class states the position
    rather than defends it.

    🔴 A CORRECTION TO THIS DOCSTRING, MEASURED BY PEER REVIEW. It said before
    that a later editor who removes the optional group "would break nothing
    that runs today". THAT IS INCORRECT AND ITS OWN FILE REFUTES IT. A mutant
    that makes the hour-and-minute group REQUIRED gives 2 failed and 19 passed
    against a control of 21 passed. One of the two failures is
    `test_the_pattern_accepts_a_date_only_heading`, which sits a few lines
    below this sentence in this class. The other is
    `test_r2_an_edit_that_adds_a_missing_marker_fires` in the gate file.

    AND THE OPTIONAL GROUP IS CORRECT AS SHIPPED, so this class records a
    position rather than a defect. The consumer alphabet is WIDER than the
    producer alphabet, because the gate reads a file a HUMAN also edits, and
    the two failure directions are not symmetric. KEEP the group, and a pin
    titled a bare date with no marker drops out of the count, which is an
    under-block on a population a user ruling declares empty. REMOVE the group,
    and a hand-written date-only entry counts as a PIN, the count rises, and a
    faithful edit to Pinned Context is DENIED. That second one is an
    over-block, which this repository treats as the cardinal direction.
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


# ---------------------------------------------------------------------------
# The bounded alphabet of `_DATE_LED_HEADING_RE`
# ---------------------------------------------------------------------------

# THE WRITER BASELINE, IN PARTS. `working_memory` builds `f"### {date_str}"`
# with `now.strftime("%Y-%m-%d %H:%M")`, so these are the writer values and the
# rendered whole is the only line the writers can produce.
_BASE = {
    "lead": "", "hashes": "###", "gap1": " ",
    "year": "2026", "sep1": "-", "month": "08", "sep2": "-", "day": "12",
    "gap2": " ", "hour": "04", "tsep": ":", "minute": "50",
    "trail": "",
}

# ONE ENTRY FOR EACH PARSE-TREE DIMENSION, AND EACH STRADDLES ITS OWN BOUND.
# The first value of each list is the writer value.
#
# 🔴 A NODE IS NOT A DIMENSION. A NODE PLUS ITS BOUNDS IS. `\s+` and `\s*` are
# the SAME parser node with different bounds, so a population that samples one
# string for each node produces identical text in the two cases and CANNOT
# witness a change of bound. Where the pattern wants four digits this generates
# three, four and five. Where it wants one or more spaces it generates zero,
# one and two. A population confined to what the pattern accepts today cannot
# report a widening.
_DIMS = {
    "lead": ["", "x "],
    "hashes": ["###", "", "#", "##", "####", "######", "#######"],
    "gap1": [" ", "", "  "],
    "year": ["2026", "202", "20268"],
    "sep1": ["-", "", "/"],
    "month": ["08", "8", "088"],
    "sep2": ["-", "", "/"],
    "day": ["12", "1", "123"],
    "gap2": [" ", "", "  "],
    "hour": ["04", "4", "044"],
    "tsep": [":", "", "."],
    "minute": ["50", "5", "500"],
    "trail": ["", " ", "  ", " Draft notes"],
}


def _render(parts):
    return (
        parts["lead"] + parts["hashes"] + parts["gap1"]
        + parts["year"] + parts["sep1"] + parts["month"]
        + parts["sep2"] + parts["day"]
        + parts["gap2"] + parts["hour"] + parts["tsep"] + parts["minute"]
        + parts["trail"]
    )


def _population():
    """Return {rendered line: (dimension, value)}.

    COUNT RULE, STATED BESIDE THE NUMBER: one case for each (dimension, value)
    pair, ONE dimension varied at a time from the writer baseline, plus the
    baseline and the whole optional group absent. One-at-a-time keeps a
    difference ATTRIBUTABLE: the case that moved names the dimension.
    """
    seen = {_render(_BASE): ("baseline", "writer")}
    no_time = dict(_BASE, gap2="", hour="", tsep="", minute="")
    seen.setdefault(_render(no_time), ("timegroup", "absent"))
    for dim, values in _DIMS.items():
        for v in values[1:]:
            seen.setdefault(_render(dict(_BASE, **{dim: v})), (dim, v))
    return seen


class TestTheDateLedPredicateAlphabetIsBounded:
    """The accepted language of `_DATE_LED_HEADING_RE`, over a generated set.

    WHY A GENERATOR RATHER THAN A CASE FOR EACH AXIS. The pinned project rule
    has two halves. The first says derive the test alphabet from the guarded
    thing. THE SECOND SAYS BOUND, DO NOT WIDEN: a widened alphabet keeps two
    spellings in sync, which is the defect's own generator, while an operator
    that makes over-reach unrepresentable has no alphabet at all. One case for
    each axis is one more thing that can drift for each axis, and the axis
    nobody enumerated stays open. ONE GENERATOR plus ONE set comparison is one
    thing that can drift, and it reports a change at ANY node without an arm
    naming that node.

    🔴 WHAT THE ACCEPTED SET IS NOT. It is NOT the set the writers can emit.
    MEASURED on the shipped pattern over this population: 6 accepted against 1
    emittable. The gate deliberately accepts five lines no writer produces, and
    each is a tolerance the pattern carries on purpose. So an arm asserting
    "accepted equals emittable" is RED on a correct tree, and the oracle has to
    name the tolerance rather than deny it.

    THE SHAPE THAT HOLDS, AND IT IS TWO-DIRECTIONAL BY CONSTRUCTION.
        accepted == emittable + DECLARED_TOLERANCE
    A WIDENING adds a member to the left and reddens. A NARROWING removes one
    and reddens. Neither direction needs an arm that names the node.

    THE BOUND, AND IT IS NOT A PROOF. This is BOUNDED-EXHAUSTIVE OVER A
    GENERATED POPULATION, not a proof about the language. The population is
    one-at-a-time from a single baseline, so it does not reach an interaction
    between two dimensions. AND THE ENUMERATION AGES: it is built from the
    pattern AS IT IS TODAY, so an edit that ADDS a node adds a dimension no
    list written today can hold. Do not read this class as coverage of the
    predicate for ever.
    """

    # The lines the shipped pattern accepts that NO writer emits. Each is a
    # deliberate tolerance. Each entry states WHY the tolerance is admitted and
    # WHAT MUST BECOME TRUE for it to be withdrawn.
    #
    # 🔴 THIS LIST IS A MITIGATION AND IT IS NOT A BAR. A reason beside an
    # entry constrains nothing a later editor writes. A person who widens the
    # pattern can add the line here, write a fluent reason for it, and this
    # class goes green. THE ABSORPTION STAYS OPEN AND THESE REASONS DO NOT
    # CLOSE IT. What they change is the SHAPE OF THE FAILURE: a silent widening
    # becomes one that requires the author to write a claim that is incorrect.
    # An omission becomes an assertion, and a reader can catch an assertion.
    #
    # SO THE ONLY CONTROL THAT CATCHES A HOLLOW REASON IS A READER. The suite
    # is green whether or not a reason here is derived, because this text
    # changes no test outcome. Do not read a passing suite as evidence that the
    # list below is bounded.
    #
    # WHY EACH REASON NAMES A COST AND A DIRECTION RATHER THAN THE FORM. A
    # reason that restates its entry is worse than no reason, because it makes
    # the list read as bounded while it stays open. So each entry states what
    # the gate does if the tolerance is REMOVED, and which way that failure
    # runs.
    #
    # THE SHARED ROOT, WHICH IS ONE FACT AND NOT FIVE. The consumer alphabet is
    # wider than the producer alphabet. `working_memory.py` emits
    # `f"### {date_str}"`, which is one space in two places and no trailing
    # space. The comment beside `_DATE_LED_HEADING_RE` states that a person
    # also writes an entry here by hand. Four mechanisms descend from that one
    # cause and they differ in COST, which is what each entry below records.
    DECLARED_TOLERANCE = {
        "### 2026-08-12": (
            "THE OPTIONAL TIME GROUP. ADMITTED because the comment beside the "
            "shipped pattern states that a person writes a date-only entry "
            "here by hand. REMOVE IT and that entry stops being date-led, so "
            "it counts as a PIN, the gate fires, and a faithful edit to Pinned "
            "Context is DENIED. That is an over-block, and the over-block is "
            "the cardinal direction. WITHDRAW IT when no date-only heading can "
            "reach the managed region, which takes two things together: each "
            "producer emits a time, AND the region takes no hand edit."
        ),
        "###  2026-08-12 04:50": (
            "A SECOND SPACE AFTER THE MARKER, at the leading run. ADMITTED "
            "because a one-space rule lets a difference no reader can count "
            "decide the verdict. REMOVE IT and a heading with two spaces stops "
            "being date-led, so a memory entry counts as a PIN and the gate "
            "over-blocks. THE TOLERANCE COSTS ONE THING ONLY: a pin titled a "
            "bare date and carrying no marker stops counting. That is the R1 "
            "population recorded at `_is_memory_entry`, and a user ruling "
            "declares it empty. WITHDRAW IT when that ruling is withdrawn, or "
            "when the region takes no hand edit."
        ),
        "### 2026-08-12  04:50": (
            "A SECOND SPACE BEFORE THE TIME. THIS IS A DIFFERENT NODE from the "
            "leading run, and it is sampled on its own because one node can "
            "move while the other holds. ADMITTED for the same cause and at "
            "the same cost as the leading run. WITHDRAW THE TWO TOGETHER: a "
            "person who tightens one node and not the other leaves the gate "
            "accepting one spelling of a heading and refusing the other, which "
            "is harder to diagnose than either rule on its own."
        ),
        "### 2026-08-12 04:50 ": (
            "A TRAILING WHITESPACE RUN. ADMITTED because the character is "
            "INVISIBLE. A person cannot see it, an editor can add or remove it "
            "without the author, and a verdict that turns on it cannot be "
            "diagnosed by the person it blocks. REMOVE IT and a file that "
            "gained one trailing space DENIES a faithful edit, with nothing on "
            "screen to explain the refusal. WITHDRAW IT when a WRITE path "
            "normalises trailing whitespace in the managed region, so the "
            "character cannot survive a write. CHECK THE WRITE PATH AND NOT "
            "THE PARSER: several readers strip on parse, and a parse-side "
            "strip does not stop the character reaching the file."
        ),
        "### 2026-08-12 04:50  ": (
            "THE SAME TRAILING NODE AT TWO SPACES, and the second sample is "
            "why this entry is here at all. ONE SAMPLE CANNOT WITNESS A CHANGE "
            "OF BOUND: one trailing space satisfies a zero-or-more run and a "
            "zero-or-one run alike, so a single sample renders identical text "
            "under the two and the comparison cannot move. Two samples "
            "separate them. ADMITTED and WITHDRAWN with the entry above, whose "
            "node it shares."
        ),
    }

    def test_the_population_straddles_the_bound_of_each_dimension(self):
        """NON-VACUITY ON THE GENERATOR, AND IT RUNS FIRST.

        A population that only ever renders the writer values cannot witness a
        change of bound, and the comparison below would then pass for ever.
        This requires each dimension to carry a value the baseline does not.
        """
        pop = _population()
        assert len(pop) > len(_DIMS), (
            f"the population is {len(pop)} cases for {len(_DIMS)} dimensions, "
            f"so at least one dimension contributed nothing"
        )
        dims_seen = {d for d, _ in pop.values()}
        missing = set(_DIMS) - dims_seen
        assert not missing, (
            f"these dimensions produced no case of their own: {sorted(missing)}. "
            f"A dimension whose variants all render to the baseline is not "
            f"sampled, and the comparison below is blind to its bound"
        )

    def test_the_pattern_accepts_what_the_writers_emit(self):
        """SOUNDNESS, ONE DIRECTION, AND IT IS THE HALF THAT PROTECTS THE USER.

        If the pattern stops accepting the writer line, memory entries count as
        pins, the gate over-blocks, and a faithful edit to Pinned Context is
        DENIED. This is the direction with a user-facing cost.
        """
        from pin_staleness_gate import _DATE_LED_HEADING_RE

        baseline = _render(_BASE)
        assert _DATE_LED_HEADING_RE.match(baseline.strip()), (
            f"_DATE_LED_HEADING_RE no longer accepts the line the writers "
            f"emit: {baseline!r}. Memory entries now count as pins and the "
            f"staleness gate OVER-BLOCKS a faithful edit"
        )

    def test_the_accepted_set_is_the_writer_line_plus_the_declared_tolerance(
        self,
    ):
        """THE LOAD-BEARING ARM. It reddens on a WIDENING and on a NARROWING.

        The left side comes from the pattern. The right side comes from the
        writers plus a tolerance list a person maintains with a reason for each
        entry. Two independent sources, one comparison.
        """
        from pin_staleness_gate import _DATE_LED_HEADING_RE

        pop = _population()
        accepted = {s for s in pop if _DATE_LED_HEADING_RE.match(s.strip())}
        expected = {_render(_BASE)} | set(self.DECLARED_TOLERANCE)

        widened = accepted - expected
        narrowed = expected - accepted

        assert not widened and not narrowed, (
            f"THE ACCEPTED LANGUAGE OF _DATE_LED_HEADING_RE HAS MOVED.\n"
            f"  WIDENED, now accepted and not declared: "
            f"{sorted((s, pop[s]) for s in widened)}\n"
            f"  NARROWED, declared and no longer accepted: "
            f"{sorted((s, pop.get(s)) for s in narrowed)}\n"
            f"\n"
            f"A WIDENING means the gate now EXCLUDES lines from the pin count "
            f"that it counted before. A curated pin can stop counting, so the "
            f"gate goes quiet on a true add, and a rename that drops a title "
            f"from the OLD side can make the gate FIRE on a faithful edit.\n"
            f"A NARROWING means the gate now COUNTS lines it excluded before, "
            f"so memory entries count as pins and a faithful edit is DENIED.\n"
            f"\n"
            f"If the change is deliberate, add or remove the entry in "
            f"DECLARED_TOLERANCE in the SAME commit, with the reason it is "
            f"correct. Do not delete this arm to go green."
        )
