"""
Location: pact-plugin/tests/test_pin_marker_writer.py

Summary: Pins the declared pinned-region START marker, its pure planner, and the
hook that writes it. Two properties are merge gates and are proven
MECHANICALLY rather than by reading the code:

  1. EXPEL-NOTHING. Every insertion is certified on DOCUMENT PAIRS -- the whole
     file before against the whole file after -- because the cap this feature
     leads to is a two-state predicate that no single-document probe can reach.
  2. NON-DENIAL. Asserted over a corpus of INPUTS driven through the real
     script as a subprocess, never over the wording of any message. The claim
     is "no input makes this hook deny", so the quantifier has to be over
     inputs.

SAFETY NOTE FOR ANYONE EDITING THIS FILE. The hook resolves a real project
CLAUDE.md and writes to it. Every test here pins CLAUDE_PROJECT_DIR to a
tmp_path so the resolver cannot reach the developer's own file, which is
gitignored and unrecoverable. Do not remove that env pin from any subprocess
call.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from shared.claude_md_manager import (
    MANAGED_END_MARKER,
    MANAGED_START_MARKER,
    MEMORY_END_MARKER,
    MEMORY_START_MARKER,
    PACT_BOUNDARY_PREFIXES,
    PINNED_START_MARKER,
)
from shared.pin_markers import (
    START_LINE,
    Insertion,
    SkipReason,
    apply_insertion,
    certify_expel_nothing,
    plan_insertion,
)

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
HOOK_SCRIPT = HOOKS_DIR / "pin_marker_writer.py"
HOOKS_JSON = HOOKS_DIR / "hooks.json"


# --------------------------------------------------------------------------
# Document builders
# --------------------------------------------------------------------------

def build_claude_md(
    pinned_body: str = "### A pin\nSome pinned prose.\n\n",
    retrieved: str = "\n### 2026-01-01\nA retrieved entry.\n\n",
    working: str = "\n### 2026-01-02\nA working entry.\n",
    user_prefix: str = "# My own heading\n\nUser prose above the block.\n\n",
    user_suffix: str = "\nUser prose below the block.\n",
    include_pinned_heading: bool = True,
    managed: bool = True,
) -> str:
    """Compose a CLAUDE.md in the canonical section order.

    Canonical order is Retrieved Context, Pinned Context, Working Memory, which
    is what puts a start marker above the pinned heading INSIDE the Retrieved
    Context span -- the reason both marker names must join the terminator
    alternation.
    """
    pinned = (
        f"## Pinned Context\n\n{pinned_body}" if include_pinned_heading else ""
    )
    body = (
        "# PACT Framework and Managed Project Memory\n\n"
        f"## Retrieved Context\n{retrieved}"
        f"{pinned}"
        f"## Working Memory\n{working}"
    )
    if not managed:
        return user_prefix + body + user_suffix
    return (
        user_prefix
        + MANAGED_START_MARKER + "\n"
        + body
        + MANAGED_END_MARKER + "\n"
        + user_suffix
    )


# --------------------------------------------------------------------------
# The two literals
# --------------------------------------------------------------------------

class TestMarkerLiterals:
    """The names are load-bearing, so their properties are pinned, not assumed."""

    def test_the_marker_joins_every_terminator_alternation(self, monkeypatch):
        """The name must be MATCHED by all three scanners that infer a
        section end.

        An unmatched start marker does not terminate the Retrieved Context
        scan. It falls inside the span that writer rebuilds from recognised
        entries only, rides the last entry as a passenger, and is deleted when
        rotation evicts that entry. A matched one terminates the scan at the
        true end of the section and lands in the span the rebuild preserves.

        The alternations are rebuilt here from each module's OWN constant --
        `PACT_BOUNDARY_PREFIXES` for the hooks side and `_PACT_BOUNDARY_ALT`
        for the skills side -- so this measures the real rule rather than a
        copy of it.
        """
        # `syspath_prepend` is reverted by pytest when the test ends. A bare
        # `sys.path.insert(0, ...)` here would OUTLIVE this test and re-order
        # imports for everything after it in the session -- the shape that
        # produced a full-suite-only failure elsewhere in this suite.
        monkeypatch.syspath_prepend(
            str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts")
        )
        from working_memory import _PACT_BOUNDARY_ALT

        hooks_alt = "|".join(PACT_BOUNDARY_PREFIXES)
        alternations = {
            "staleness pinned scan": re.compile(
                rf'(?:#{{1,2}}\s|<!-- (?:{hooks_alt}))'
            ),
            "working memory scan": re.compile(
                rf'(#\s|##\s(?!Working Memory)|---|<!-- (?:{_PACT_BOUNDARY_ALT}))'
            ),
            "retrieved context scan": re.compile(
                rf'(#\s|##\s(?!Retrieved Context)|---|<!-- (?:{_PACT_BOUNDARY_ALT}))'
            ),
        }
        for marker in (PINNED_START_MARKER,):
            for name, pattern in alternations.items():
                assert pattern.match(marker), (
                    f"{marker} is NOT matched by the {name}. An unmatched "
                    "marker is deleted by section rotation."
                )

    def test_alternation_check_is_not_vacuous(self):
        """A name the alternation does NOT match must fail the same check.

        Without this, a pattern that matched everything would pass the test
        above while measuring nothing.
        """
        hooks_alt = "|".join(PACT_BOUNDARY_PREFIXES)
        pattern = re.compile(rf'(?:#{{1,2}}\s|<!-- (?:{hooks_alt}))')
        assert not pattern.match("<!-- PINNED_START -->")
        assert not pattern.match("<!-- PACT_PINNED_START -->")

    @pytest.mark.parametrize("existing", [
        MANAGED_START_MARKER, MANAGED_END_MARKER,
        MEMORY_START_MARKER, MEMORY_END_MARKER,
    ])
    def test_new_literals_contain_no_existing_marker_as_substring(self, existing):
        """Containment either way would be a live bug, not an aesthetic one.

        `extract_managed_region` uses first-find on the managed markers, so a
        literal containing one would mis-anchor or truncate the region. And
        session_resume runs an UNBOUNDED replace on the memory start marker, so
        a literal containing THAT would collect a session block on every
        SessionStart.
        """
        for new in (PINNED_START_MARKER,):
            assert existing not in new
            assert new not in existing

    def test_marker_line_is_the_marker_plus_one_newline(self):
        assert START_LINE == PINNED_START_MARKER + "\n"


# --------------------------------------------------------------------------
# MERGE GATE 1 -- EXPEL-NOTHING, on document pairs
# --------------------------------------------------------------------------

PIN_TABLE = [
    ("single pin", "### A pin\nbody\n\n"),
    ("two pins", "### One\nbody one\n\n### Two\nbody two\n\n"),
    ("pin with a stamp", "### A pin\n<!-- pinned: 2026-01-01 -->\nbody\n\n"),
    ("body ends in blank lines", "### A pin\nbody\n\n\n\n"),
    ("body with no trailing blank", "### A pin\nbody\n"),
    ("prose with no H3 at all", "Just prose, no entry heading.\n\n"),
    ("body containing an html comment", "### A pin\n<!-- a note -->\nbody\n\n"),
    # A FENCED BODY IS NOT IN THIS TABLE ON PURPOSE. Every row here must produce
    # an insertion, and a fenced body is now REFUSED outright. The refusal and
    # the shapes that forced it are pinned in TestFencedBodyRefusal below.
    ("unicode body", "### A pin\nnaive cafe resume\n\n"),
    ("very long body", "### A pin\n" + ("x" * 5000) + "\n\n"),
    ("body with windows line endings", "### A pin\r\nbody\r\n\r\n"),
    ("body with a tab", "### A pin\n\tindented\n\n"),
    ("body with an equals rule", "### A pin\nbody\n===\n\n"),
]


class TestExpelNothing:
    """The certificate, driven on whole documents rather than on lines."""

    @pytest.mark.parametrize("label,pinned_body", PIN_TABLE, ids=[r[0] for r in PIN_TABLE])
    def test_insertion_expels_nothing(self, label, pinned_body):
        old = build_claude_md(pinned_body=pinned_body)
        planned = plan_insertion(old)
        assert isinstance(planned, Insertion), (
            f"{label}: expected an insertion, got {planned}"
        )
        new = apply_insertion(old, planned)

        # The certificate itself.
        assert certify_expel_nothing(old, new, planned) is True

        # Restated independently of the function under test, so a certificate
        # that silently degraded to `return True` cannot carry this test.
        assert len(new) == len(old) + len(START_LINE)
        assert new.replace(START_LINE, "") == old

        # Every original character survives in its original order.
        assert old in new.replace(START_LINE, "")

    @pytest.mark.parametrize("label,pinned_body", PIN_TABLE, ids=[r[0] for r in PIN_TABLE])
    def test_the_marker_lands_in_the_right_place(self, label, pinned_body):
        """Placement is pinned SEPARATELY, and it is now the ONLY thing
        constraining the offset at all.

        MEASURED: with a single splice point the certificate returns True at
        EVERY offset from 0 to len(old) -- a splice point cannot cross itself,
        so no offset can drop a byte. Before the end marker was removed the
        offset had two independent constraints, the certificate refusing
        crossed offsets and these assertions. Now it has one. If this test is
        weakened or deleted, nothing anywhere checks where the marker went.
        """
        old = build_claude_md(pinned_body=pinned_body)
        planned = plan_insertion(old)
        new = apply_insertion(old, planned)

        # The marker sits immediately ABOVE the pinned heading, on its own line.
        after_marker = new.split(START_LINE, 1)[1]
        assert after_marker.startswith("## Pinned Context"), (
            f"{label}: the line after the marker is not the pinned heading"
        )

        # It sits BELOW the retrieved-context section it terminates, so the
        # heading it declares is the pinned one and not some earlier section.
        before_marker = new.split(START_LINE, 1)[0]
        assert before_marker.endswith("\n"), (
            f"{label}: the marker does not begin its own line"
        )
        assert "## Retrieved Context" in before_marker

        # The whole pinned body still follows it, unmoved.
        assert pinned_body.strip()[:20] in after_marker

    def test_placement_assertions_can_actually_fail(self):
        """NON-VACUITY FOR PLACEMENT, and it exists because of what the END
        removal took away.

        The retired crossed-offset arm proved the CERTIFICATE could refuse a
        bad offset. With one splice point that arm is unconstructible -- there
        is no second offset to cross -- and the certificate accepts every
        offset. So placement became the sole offset constraint, and it was the
        only guard in this file with nothing proving it can redden.

        This is the heir to that arm. It builds a deliberately wrong placement,
        shows the CERTIFICATE ACCEPTS it, and shows the placement assertion
        REJECTS it. Do NOT read this as a duplicate of the happy-path placement
        test above and delete it: that test proves the good case passes, this
        one proves the bad case is caught, and only together do they constrain
        anything.
        """
        old = build_claude_md()
        wrong = Insertion(start_offset=0, start_line=START_LINE)
        damaged = apply_insertion(old, wrong)

        # The certificate is perfectly happy with it.
        assert certify_expel_nothing(old, damaged, wrong) is True, (
            "if this ever fails, the certificate has regained an offset "
            "constraint and placement is no longer the sole guard"
        )

        # The placement assertion is not.
        after_marker = damaged.split(START_LINE, 1)[1]
        assert not after_marker.startswith("## Pinned Context"), (
            "the deliberately wrong placement was not detectable, so the "
            "placement assertions cannot catch a misplaced marker"
        )

    def test_certificate_refuses_a_composition_that_drops_bytes(self):
        """NON-VACUITY for the certificate. It must REFUSE a real defect, or
        its green means nothing.

        The defect it can still catch is a MIS-ASSEMBLED composition, not a bad
        offset. `apply_insertion` is now the only place a byte-losing bug can
        enter, so the mutation is applied there: this splice drops one byte.
        """
        old = build_claude_md()
        good = plan_insertion(old)
        assert isinstance(good, Insertion)

        # A byte-dropping splice -- the shape a careless edit to
        # `apply_insertion` would produce.
        o = good.start_offset
        damaged = old[:o] + START_LINE + old[o + 1:]

        # The damage is real: content was actually lost.
        assert len(damaged) != len(old) + len(START_LINE)
        assert certify_expel_nothing(old, damaged, good) is False

    @pytest.mark.parametrize("label,mutate", [
        ("drops a byte", lambda c, o: c[:o] + START_LINE + c[o + 1:]),
        ("duplicates a byte", lambda c, o: c[:o + 1] + START_LINE + c[o:]),
        ("inserts the marker twice", lambda c, o: c[:o] + START_LINE + START_LINE + c[o:]),
        ("omits the newline", lambda c, o: c[:o] + START_LINE.rstrip("\n") + c[o:]),
        ("reorders the tail", lambda c, o: c[:o] + START_LINE + c[o:][::-1]),
    ])
    def test_every_assembly_mutation_is_refused(self, label, mutate):
        """The certificate's real remaining scope, enumerated.

        Each of these is a way `apply_insertion` could be broken by a future
        edit. All must be refused; the correct assembly is the control below.
        """
        old = build_claude_md()
        good = plan_insertion(old)
        assert certify_expel_nothing(
            old, mutate(old, good.start_offset), good
        ) is False, f"{label} was NOT refused"

    def test_the_correct_assembly_is_accepted(self):
        """CONTROL for the mutation table above. Without it, a certificate that
        refused everything would pass every row while blocking every write."""
        old = build_claude_md()
        good = plan_insertion(old)
        assert certify_expel_nothing(old, apply_insertion(old, good), good) is True

    def test_certificate_refuses_when_the_file_already_quotes_a_marker(self):
        """Driven DIRECTLY, because in the assembled write the presence check
        in `plan_insertion` refuses this file earlier.

        The two mechanisms are independent on purpose and neither may be
        removed on the ground that the other covers it, so each is pinned on
        its own.
        """
        old = build_claude_md(
            pinned_body="### A pin\nI wrote " + START_LINE + "in my notes\n\n"
        )
        forced = Insertion(0, START_LINE)
        new = apply_insertion(old, forced)
        assert certify_expel_nothing(old, new, forced) is False

    def test_certificate_never_raises(self):
        forced = Insertion(0, START_LINE)
        assert certify_expel_nothing(None, None, forced) is False
        assert certify_expel_nothing(1, 2, forced) is False


# --------------------------------------------------------------------------
# The precondition ladder and ordered-pair idempotence
# --------------------------------------------------------------------------

class TestPreconditionLadder:

    def test_unmigrated_file_is_refused(self):
        doc = build_claude_md(managed=False)
        assert plan_insertion(doc) is SkipReason.NOT_MIGRATED

    def test_absent_pinned_section_is_a_noop(self):
        doc = build_claude_md(include_pinned_heading=False)
        assert plan_insertion(doc) is SkipReason.NO_SECTION

    @pytest.mark.parametrize("body", ["", "   \n\n", "\n", "\t\n \n"])
    def test_empty_pinned_section_is_a_noop(self, body):
        """An empty section reads as ABSENT to the only current reader of this
        region, so a pair around it would declare a boundary no consumer
        believes in. Such a heading is migration-emitted, so this skips a
        heading the plugin wrote, never a user's content.
        """
        doc = build_claude_md(pinned_body=body)
        assert plan_insertion(doc) is SkipReason.EMPTY_SECTION

    def test_plan_never_raises_on_a_non_string(self):
        assert plan_insertion(None) is SkipReason.PLAN_FAILED
        assert plan_insertion(42) is SkipReason.PLAN_FAILED

    def test_no_pinned_section_means_the_section_is_never_created(self):
        """The 'create the missing section' shape is the destructive one, so
        its absence is asserted rather than assumed."""
        doc = build_claude_md(include_pinned_heading=False)
        planned = plan_insertion(doc)
        assert isinstance(planned, SkipReason)
        assert "## Pinned Context" not in doc


class TestFencedBodyRefusal:
    """A pinned body containing ANY fence marker is refused.

    THE PREDICATE IS A BARE SUBSTRING TEST AND THAT IS THE POINT. The
    terminator scan has no fence awareness, and the guarantee it relies on --
    that the managed region holds only plugin-generated content -- is FALSE for
    the pinned section, where pins are user-authored. So on a fenced body the
    offset it returns cannot be trusted.

    The intuitive repair is a backtick tracker that finds the first terminator
    OUTSIDE a fence, plus a refusal gate for ambiguous cases. It was measured
    and it FAILS, and the two failures below are why this suite pins them by
    name. Crucially the refusal gate does not save that design either, because
    the gate asks the SAME tracker whether the landing line is inside a fence:
    on these shapes the tracker believes it is not, so the gate stays silent
    exactly where it is needed. A guard that consults the mechanism it guards
    cannot catch that mechanism failing.
    """

    FENCED_SHAPES = [
        ("backtick fence with a heading inside",
         "### A pin\n```\n## Not a heading\n```\nmore\n\n"),
        ("balanced fence with a heading-shaped line",
         "### A pin\n```\n# install deps\n```\nmore\n\n"),
        ("unclosed fence",
         "### A pin\n```\ncode that never closes\n\n"),
        ("four backticks wrapping three",
         "### A pin\n````\n```\n## Inner\n```\n````\nmore\n\n"),
        ("tilde fence containing a heading-shaped line",
         "### A pin\n~~~\n## Not a heading\n~~~\nmore\n\n"),
        ("balanced fence with no heading inside",
         "### A pin\n```\nplain code\n```\nmore\n\n"),
        ("inline triple backtick in prose",
         "### A pin\nuse ``` to open a block\n\n"),
    ]

    @pytest.mark.parametrize(
        "label,body", FENCED_SHAPES, ids=[r[0] for r in FENCED_SHAPES]
    )
    def test_every_fenced_shape_is_refused(self, label, body):
        doc = build_claude_md(pinned_body=body)
        assert plan_insertion(doc) is SkipReason.FENCED_BODY, (
            f"{label}: a fenced body must be refused, never placed"
        )

    def test_an_unfenced_body_is_still_inserted(self):
        """NON-VACUITY. A predicate that refused everything would pass every
        assertion above while shipping a write that never runs.
        """
        doc = build_claude_md(pinned_body="### A pin\nplain prose only\n\n")
        assert isinstance(plan_insertion(doc), Insertion)

    def test_the_refusal_is_what_prevents_the_misplacement(self):
        """Shows the defect the refusal avoids, so a later reader can see what
        is at stake before narrowing the predicate.

        The fence-blind scan really does stop on the heading-shaped line INSIDE
        the user's fence. Were the body not refused, the end marker would be
        placed there, splitting the user's code block.
        """
        from shared.claude_md_manager import extract_managed_region
        from shared.pin_markers import _PINNED_HEADING, _PINNED_TERMINATOR
        from staleness import _find_terminator_offset

        doc = build_claude_md(
            pinned_body="### A pin\n```\n## Not a heading\n```\nmore\n\n"
        )
        region_text, _start = extract_managed_region(doc)
        heading = _PINNED_HEADING.search(region_text)
        end = _find_terminator_offset(
            region_text, heading.end(), _PINNED_TERMINATOR
        )
        assert region_text[end:].startswith("## Not a heading")

    def test_no_reader_was_taught_about_fences(self):
        """PR A changes NO reader. Repairing `_find_terminator_offset` would be
        an extent-contract change: on a currently-truncated pinned region a
        more complete reader RAISES the observed pin count, which can cross a
        count threshold and produce an over-block introduced BY the repair.

        The check is for a fence DELIMITER LITERAL, not for the word "fence".
        `staleness.py` already explains in prose why it does no fence tracking,
        so the word is present and is not evidence of logic. A real fence
        handler cannot be written without one of these literals, which makes
        their absence the load-bearing signal.
        """
        source = (HOOKS_DIR / "staleness.py").read_text(encoding="utf-8")
        for delimiter in ("```", "~~~"):
            assert delimiter not in source, (
                f"staleness.py contains the fence delimiter {delimiter!r}: a "
                "reader was taught about fences, which is an extent-contract "
                "change and does not belong in this PR"
            )


TERMINATOR_CORPUS = [
    ("h2 heading", "## Working Memory\n\n### 2026-01-02\nentry\n"),
    ("h1 heading", "# A top-level heading\n\nprose\n"),
    ("memory boundary", "<!-- PACT_MEMORY_END -->\n\nafter\n"),
    ("routing boundary", "<!-- PACT_ROUTING_START -->\n\nafter\n"),
    ("no terminator at all", ""),
    ("h3 is not a terminator", "### Not a terminator\nprose\n"),
    ("horizontal rule is not one", "---\nprose\n"),
    ("indented h2 is not one", "  ## Indented\nprose\n"),
    ("h2 with no space is not one", "##NoSpace\nprose\n"),
]


class TestTerminatorParityWithTheReader:
    """THE TWIN GUARD.

    `pin_markers` compiles the same terminator SHAPE that
    `staleness._parse_pinned_section` compiles inline. Two definitions of
    "where does a section end" is precisely the drift these markers exist to
    close, so reintroducing it unguarded would be self-defeating.

    The guard pins BEHAVIOUR, not pattern source. A source comparison fires on
    a semantically identical rewrite, and a guard that reddens on harmless
    edits gets weakened or deleted -- which is how the real coverage dies. So
    this drives BOTH implementations over a corpus of whole documents and
    compares the offset each one lands on. The reader is exercised through its
    own real function rather than through a copy of its regex.

    The property is the one that actually matters: THE BOUNDARY THIS WRITE
    DECLARES MUST BE THE BOUNDARY THE CURRENT READER INFERS. If those ever
    disagree, the markers stop describing the region they wrap.
    """

    @pytest.mark.parametrize(
        "label,tail", TERMINATOR_CORPUS, ids=[r[0] for r in TERMINATOR_CORPUS]
    )
    def test_the_planners_body_extent_equals_the_readers(self, label, tail):
        """RE-ANCHORED after the END marker was removed, and the re-anchoring
        is the point.

        This guard used to compare the offset the write DECLARED against the
        offset the reader INFERRED. There is no declared end any more, so that
        comparison has no left-hand side. The twin-drift RISK did not go away
        with it: this planner still compiles its own terminator, and still uses
        it to decide whether the body is empty and whether it is fenced. What
        changed is the CONSEQUENCE of drift, not its possibility.

        So the property moves to the extent both implementations measure. If
        the two terminators ever disagree, the planner and the live reader see
        different pinned bodies, and this reddens.
        """
        from staleness import _parse_pinned_section
        from shared.claude_md_manager import extract_managed_region
        from shared.pin_markers import _PINNED_HEADING, _PINNED_TERMINATOR
        from staleness import _find_terminator_offset

        doc = (
            "# User heading\n\n"
            + MANAGED_START_MARKER + "\n"
            + "## Pinned Context\n\n### A pin\nbody prose\n\n"
            + tail
            + MANAGED_END_MARKER + "\ntrailing\n"
        )
        parsed = _parse_pinned_section(doc)
        assert parsed is not None, f"{label}: the reader found no pinned section"

        region_text, _start = extract_managed_region(doc)
        heading = _PINNED_HEADING.search(region_text)
        planner_body = region_text[
            heading.end():
            _find_terminator_offset(region_text, heading.end(), _PINNED_TERMINATOR)
        ]
        assert planner_body == parsed[2], (
            f"{label}: the planner measures a different pinned body than the "
            "reader infers. The two terminator definitions have drifted."
        )

    def test_the_parity_check_can_actually_fail(self, monkeypatch):
        """NON-VACUITY, by mutating the twin rather than the caller.

        Without this arm a parity test that compared a value to itself would
        pass forever while guarding nothing.
        """
        import shared.pin_markers as pin_markers
        from staleness import _parse_pinned_section, _find_terminator_offset
        from shared.claude_md_manager import extract_managed_region

        doc = (
            "# User heading\n\n"
            + MANAGED_START_MARKER + "\n"
            + "## Pinned Context\n\n### A pin\nbody prose\n\n"
            + "## Working Memory\n\nentry\n"
            + MANAGED_END_MARKER + "\ntrailing\n"
        )

        def planner_body():
            region_text, _s = extract_managed_region(doc)
            h = pin_markers._PINNED_HEADING.search(region_text)
            return region_text[
                h.end():
                _find_terminator_offset(
                    region_text, h.end(), pin_markers._PINNED_TERMINATOR
                )
            ]

        # Sanity: they agree before the mutation.
        assert planner_body() == _parse_pinned_section(doc)[2]

        # Mutate the planner's terminator so it no longer stops on an H2.
        monkeypatch.setattr(
            pin_markers, "_PINNED_TERMINATOR",
            re.compile(r'(?:<!-- (?:PACT_MEMORY_|PACT_MANAGED_|PACT_ROUTING_))'),
        )
        assert planner_body() != _parse_pinned_section(doc)[2], (
            "the mutated planner still agreed with the reader, so the parity "
            "assertion cannot detect drift"
        )


class TestIdempotenceOnASingleMarker:
    """Idempotence for ONE marker is a PRESENCE check and nothing more.

    The state space is exactly two -- the marker is in the file or it is not.
    There is no ordering to verify and no unpaired case to name, because
    ordering needs two things to order. The former `inverted_pair` and
    `unpaired` outcomes described states only a pair could occupy and were
    DELETED rather than left unreachable behind a comment.
    """

    def test_second_pass_is_a_noop(self):
        old = build_claude_md()
        once = apply_insertion(old, plan_insertion(old))
        assert plan_insertion(once) is SkipReason.ALREADY_MARKED

    def test_third_pass_is_still_a_noop(self):
        old = build_claude_md()
        once = apply_insertion(old, plan_insertion(old))
        assert plan_insertion(once) is SkipReason.ALREADY_MARKED
        assert plan_insertion(once) is SkipReason.ALREADY_MARKED

    def test_repeated_application_never_doubles_the_marker(self):
        old = build_claude_md()
        text = old
        for _ in range(4):
            planned = plan_insertion(text)
            if isinstance(planned, Insertion):
                text = apply_insertion(text, planned)
        assert text.count(PINNED_START_MARKER) == 1

    def test_a_lone_marker_is_the_intended_state_not_an_error(self):
        """A file carrying this marker and no closing one is CORRECT.

        Pinned explicitly because the previous shape treated exactly this
        document as `unpaired` -- an error state. Anything that reintroduces
        that reading is now wrong, so this test names the reversal rather than
        relying on the absent branch being noticed.
        """
        old = build_claude_md()
        marked = apply_insertion(old, plan_insertion(old))
        assert marked.count(PINNED_START_MARKER) == 1
        outcome = plan_insertion(marked)
        assert outcome is SkipReason.ALREADY_MARKED
        assert outcome is not SkipReason.PLAN_FAILED
        assert not hasattr(SkipReason, "UNPAIRED")
        assert not hasattr(SkipReason, "INVERTED_PAIR")

    def test_presence_is_detected_wherever_the_marker_sits(self):
        """NON-VACUITY for the presence check: a marker anywhere in the file
        must be seen, so the check cannot be an accident of position."""
        old = build_claude_md()
        for placed in (
            START_LINE + old,
            old.replace("## Working Memory", START_LINE + "## Working Memory"),
            old + START_LINE,
        ):
            assert plan_insertion(placed) is SkipReason.ALREADY_MARKED


# --------------------------------------------------------------------------
# MERGE GATE 2 -- non-denial, quantified over INPUTS
# --------------------------------------------------------------------------

def run_hook(frame, tmp_path, timeout=30):
    """Drive the REAL script as a subprocess and return (rc, stdout, stderr).

    CLAUDE_PROJECT_DIR is pinned to tmp_path so the resolver cannot reach the
    developer's own CLAUDE.md. Do not remove that.
    """
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "config"),
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(frame) if not isinstance(frame, str) else frame,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


# Every one of these is an INPUT the hook may be handed. The assertion below
# is quantified over this set, not over any message's wording.
DENIAL_CORPUS = [
    ("empty stdin", ""),
    ("not json", "this is not json at all"),
    ("json but not an object", "[1, 2, 3]"),
    ("json null", "null"),
    ("json string", '"a bare string"'),
    ("empty object", {}),
    ("no prompt key", {"hook_event_name": "UserPromptSubmit"}),
    ("prompt is not a string", {"hook_event_name": "UserPromptSubmit", "prompt": 42}),
    ("prompt is null", {"hook_event_name": "UserPromptSubmit", "prompt": None}),
    ("ordinary prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "hello there"}),
    ("near-miss command", {"hook_event_name": "UserPromptSubmit",
                           "prompt": "/PACT:pin-memory-something"}),
    ("real pin command", {"hook_event_name": "UserPromptSubmit",
                          "prompt": "/PACT:pin-memory some context"}),
    ("real prune command", {"hook_event_name": "UserPromptSubmit",
                            "prompt": "/PACT:prune-memory"}),
    ("tool_input not a dict", {"hook_event_name": "PostToolUse", "tool_input": "nope"}),
    ("skill not a string", {"hook_event_name": "PostToolUse",
                            "tool_input": {"skill": []}}),
    ("skill route", {"hook_event_name": "PostToolUse",
                     "tool_input": {"skill": "PACT:pin-memory"}}),
    ("unrelated skill", {"hook_event_name": "PostToolUse",
                         "tool_input": {"skill": "some-other-skill"}}),
    ("hostile event name", {"hook_event_name": {"nested": "dict"}, "prompt": "hi"}),
    ("huge prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "x" * 100000}),
    ("prompt with null bytes", {"hook_event_name": "UserPromptSubmit",
                                "prompt": "/PACT:pin-memory \x00\x01"}),
]

# Tokens that would constitute a block decision on either channel.
DENIAL_TOKENS = (
    '"decision"', '"block"', '"deny"', '"permissionDecision"',
    '"continue": false', '"continue":false', '"stopReason"',
)


class TestCannotDeny:
    """Merge gate 2. The claim is 'no input makes this hook deny', so the
    quantifier is over inputs.
    """

    @pytest.mark.parametrize("label,frame", DENIAL_CORPUS, ids=[r[0] for r in DENIAL_CORPUS])
    def test_exit_code_is_zero_for_every_input(self, label, frame, tmp_path):
        """Exit 2 is the block code on both registered channels, and any
        non-zero exit reaching the block path is indistinguishable from a
        deliberate refusal. So the assertion is exit code EQUALS zero, not
        merely 'not 2'.
        """
        rc, out, err = run_hook(frame, tmp_path)
        assert rc == 0, (
            f"{label}: exit {rc}. A non-zero exit on UserPromptSubmit blocks "
            f"the user's prompt. stderr={err[:400]}"
        )

    @pytest.mark.parametrize("label,frame", DENIAL_CORPUS, ids=[r[0] for r in DENIAL_CORPUS])
    def test_no_block_decision_is_emitted_for_any_input(self, label, frame, tmp_path):
        rc, out, err = run_hook(frame, tmp_path)
        for token in DENIAL_TOKENS:
            assert token not in out, (
                f"{label}: stdout carries {token}, which is a block decision"
            )

    @pytest.mark.parametrize("label,frame", DENIAL_CORPUS, ids=[r[0] for r in DENIAL_CORPUS])
    def test_output_is_a_valid_suppress_envelope(self, label, frame, tmp_path):
        """Every emit path must carry hookEventName. A missing or unknown one
        is a SILENT schema rejection at the platform layer.
        """
        rc, out, err = run_hook(frame, tmp_path)
        assert out.strip(), f"{label}: no output at all"
        payload = json.loads(out)
        assert payload["suppressOutput"] is True
        assert payload["hookSpecificOutput"]["hookEventName"]

    def test_the_denial_corpus_can_observe_a_denial(self, tmp_path):
        """POSITIVE CONTROL for the two assertions above.

        A script that DOES deny must fail both of them. Without this, an
        assertion that could never fire would carry the merge gate.
        """
        denier = tmp_path / "denier.py"
        denier.write_text(
            "import sys\n"
            'print(\'{"decision": "block"}\')\n'
            "sys.exit(2)\n"
        )
        proc = subprocess.run(
            [sys.executable, str(denier)], input="{}", capture_output=True,
            text=True, timeout=30,
        )
        assert proc.returncode == 2
        assert any(token in proc.stdout for token in DENIAL_TOKENS)

    def test_the_echoed_event_name_follows_the_firing_event(self, tmp_path):
        """The two registrations fire under different event names, so a
        hard-coded value would be a silent rejection on one of them."""
        for event in ("UserPromptSubmit", "PostToolUse"):
            rc, out, err = run_hook(
                {"hook_event_name": event, "prompt": "hello"}, tmp_path
            )
            assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == event


# --------------------------------------------------------------------------
# The hot path: nothing from the plugin is imported before the command test
# --------------------------------------------------------------------------

class TestAgentRouteSkillNameShape:
    """The shape a `Skill` invocation actually delivers.

    MEASURED 2026-08-01 in an isolated frame on this platform build: a PLUGIN
    skill arrives PLUGIN-QUALIFIED (`PACT:bootstrap` was observed) while a
    PROJECT-level skill arrives bare (`probeskill`). Both pin commands are
    plugin skills, so they arrive qualified.

    This is pinned as a test rather than left in a comment because it closed an
    open uncertainty by measurement: a bare-name widening had been refused on
    judgement, and the measurement showed the widening would have been both
    unnecessary AND actively wrong, since it would have matched another
    plugin's same-named skill. An uncertainty closed by measurement should not
    be able to silently re-open.
    """

    @pytest.mark.parametrize("skill_value", [
        "PACT:pin-memory", "PACT:prune-memory",
        "/PACT:pin-memory", "/PACT:prune-memory",
    ])
    def test_qualified_names_are_accepted(self, skill_value, tmp_path):
        original = build_claude_md()
        (tmp_path / "CLAUDE.md").write_text(original, encoding="utf-8")
        rc, out, err = run_hook(
            {"hook_event_name": "PostToolUse",
             "tool_input": {"skill": skill_value}},
            tmp_path,
        )
        assert rc == 0
        written = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert PINNED_START_MARKER in written, (
            f"{skill_value} is a pin command and must reach the write"
        )

    @pytest.mark.parametrize("skill_value", [
        "pin-memory", "prune-memory",          # bare: another plugin could own these
        "OTHER:pin-memory", "PACT:pin-memory-x", "PACT:something-else",
    ])
    def test_unqualified_and_foreign_names_are_refused(
        self, skill_value, tmp_path
    ):
        original = build_claude_md()
        (tmp_path / "CLAUDE.md").write_text(original, encoding="utf-8")
        rc, out, err = run_hook(
            {"hook_event_name": "PostToolUse",
             "tool_input": {"skill": skill_value}},
            tmp_path,
        )
        assert rc == 0
        assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == original, (
            f"{skill_value} must NOT reach the write: the write is reachable "
            "only through a confirmed invocation of the two pin commands"
        )


class TestHotPath:

    def test_module_level_imports_are_stdlib_only(self):
        """A module-level plugin import moves failure BEFORE the command test,
        which is the one ordering this hook cannot lose. On a channel that
        fires for every prompt, that turns a plugin bug into a session-wide
        outage. Asserted structurally, on the AST, so it cannot rot.
        """
        tree = ast.parse(HOOK_SCRIPT.read_text(encoding="utf-8"))
        plugin_roots = {"shared", "staleness", "pin_caps", "pact_context"}
        offenders = []
        for node in tree.body:  # MODULE level only
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                targets = [node.module or ""]
            elif isinstance(node, ast.Try):
                for sub in node.body:
                    if isinstance(sub, ast.Import):
                        targets += [a.name for a in sub.names]
                    elif isinstance(sub, ast.ImportFrom):
                        targets.append(sub.module or "")
            for name in targets:
                if name.split(".")[0] in plugin_roots:
                    offenders.append(name)
        assert offenders == [], (
            f"module-level plugin imports found: {offenders}. They must sit "
            "below the command test."
        )

    def test_hook_carries_no_banned_discriminator_or_literal(self):
        source = HOOK_SCRIPT.read_text(encoding="utf-8")
        for banned in ("is_lead", "resolve_agent_name", "session_registry"):
            assert banned not in source, (
                f"{banned} is banned in this hook: the marker write applies to "
                "every editor, with no role or frame check"
            )


# --------------------------------------------------------------------------
# End to end, through the real script and the real filesystem
# --------------------------------------------------------------------------

class TestEndToEnd:

    def _project(self, tmp_path, content):
        (tmp_path / "CLAUDE.md").write_text(content, encoding="utf-8")
        return tmp_path / "CLAUDE.md"

    def test_pin_command_writes_the_marker_and_changes_nothing_else(self, tmp_path):
        original = build_claude_md()
        target = self._project(tmp_path, original)

        rc, out, err = run_hook(
            {"hook_event_name": "UserPromptSubmit",
             "prompt": "/PACT:pin-memory remember this"},
            tmp_path,
        )
        assert rc == 0
        written = target.read_text(encoding="utf-8")
        assert written != original, "the write did not happen"
        assert PINNED_START_MARKER in written
        # The same certificate the writer applies, re-applied from outside.
        assert len(written) == len(original) + len(START_LINE)
        assert written.replace(START_LINE, "") == original

    def test_an_ordinary_prompt_does_not_touch_the_file(self, tmp_path):
        original = build_claude_md()
        target = self._project(tmp_path, original)
        rc, out, err = run_hook(
            {"hook_event_name": "UserPromptSubmit", "prompt": "what time is it"},
            tmp_path,
        )
        assert rc == 0
        assert target.read_text(encoding="utf-8") == original

    def test_a_near_miss_command_does_not_touch_the_file(self, tmp_path):
        original = build_claude_md()
        target = self._project(tmp_path, original)
        rc, out, err = run_hook(
            {"hook_event_name": "UserPromptSubmit",
             "prompt": "/PACT:pin-memory-not-really"},
            tmp_path,
        )
        assert rc == 0
        assert target.read_text(encoding="utf-8") == original

    def test_a_file_with_no_pinned_section_is_left_alone(self, tmp_path):
        original = build_claude_md(include_pinned_heading=False)
        target = self._project(tmp_path, original)
        rc, out, err = run_hook(
            {"hook_event_name": "UserPromptSubmit", "prompt": "/PACT:pin-memory"},
            tmp_path,
        )
        assert rc == 0
        assert target.read_text(encoding="utf-8") == original
        assert "## Pinned Context" not in target.read_text(encoding="utf-8")

    def test_running_twice_writes_the_marker_exactly_once(self, tmp_path):
        original = build_claude_md()
        target = self._project(tmp_path, original)
        for _ in range(3):
            rc, out, err = run_hook(
                {"hook_event_name": "UserPromptSubmit",
                 "prompt": "/PACT:pin-memory"},
                tmp_path,
            )
            assert rc == 0
        written = target.read_text(encoding="utf-8")
        assert written.count(PINNED_START_MARKER) == 1

    def test_a_fenced_pinned_body_is_left_untouched(self, tmp_path):
        original = build_claude_md(
            pinned_body="### A pin\n```\n## Not a heading\n```\nmore\n\n"
        )
        target = self._project(tmp_path, original)
        rc, out, err = run_hook(
            {"hook_event_name": "UserPromptSubmit", "prompt": "/PACT:pin-memory"},
            tmp_path,
        )
        assert rc == 0
        assert target.read_text(encoding="utf-8") == original
        assert PINNED_START_MARKER not in target.read_text(encoding="utf-8")

    def test_absent_claude_md_is_never_created(self, tmp_path):
        """The hook must not bring the file into being under any circumstance."""
        rc, out, err = run_hook(
            {"hook_event_name": "UserPromptSubmit", "prompt": "/PACT:pin-memory"},
            tmp_path,
        )
        assert rc == 0
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

class TestFencedBodyCensusEvent:
    """The refusal emits a countable signal.

    The frequency of a fenced pinned body has been measured on ONE disk, by the
    same people who chose the predicate -- a self-applied control over a single
    population. This event turns it into a live count across every consumer,
    and it arrives before anything decides to trust the declared boundary.
    """

    def _capture(self, monkeypatch, outcome):
        import shared.pact_context as pact_context
        import shared.session_journal as session_journal
        import pin_marker_writer

        events = []
        monkeypatch.setattr(session_journal, "append_event",
                            lambda event: events.append(event) or True)
        monkeypatch.setattr(pact_context, "init", lambda frame: None)
        pin_marker_writer._journal({}, "typed", "PACT:pin-memory", outcome)
        return events

    def test_a_fenced_skip_emits_the_census_event(self, monkeypatch):
        events = self._capture(monkeypatch, SkipReason.FENCED_BODY.value)
        types = [e["type"] for e in events]
        assert "pin_marker_write" in types
        assert "fenced_body_skipped" in types

    def test_the_census_event_carries_no_file_content(self, monkeypatch):
        events = self._capture(monkeypatch, SkipReason.FENCED_BODY.value)
        census = next(e for e in events if e["type"] == "fenced_body_skipped")
        assert set(census) == {"v", "type", "ts", "route", "command"}
        assert census["route"] == "typed"
        assert census["command"] == "PACT:pin-memory"

    def test_the_census_event_records_a_DECLINED_decision_not_a_guess(
        self, monkeypatch
    ):
        """It must NOT carry what the boundary "would have been". The only
        mechanism able to compute that is the fence tracker measured to be
        wrong on real shapes, so such a field would be a fabricated
        measurement -- worse than none, because it would read as data.
        """
        events = self._capture(monkeypatch, SkipReason.FENCED_BODY.value)
        census = next(e for e in events if e["type"] == "fenced_body_skipped")
        for forbidden in ("offset", "end_offset", "divergence", "would_have",
                          "fence_aware", "body", "content", "path"):
            assert not any(forbidden in key for key in census), (
                f"the census event carries {forbidden!r}, which would be a "
                "computed guess rather than a record of a declined decision"
            )

    @pytest.mark.parametrize("outcome", [
        "written", "noop_no_section", "noop_empty_section", "already_marked",
    ])
    def test_other_outcomes_do_not_emit_the_census_event(
        self, monkeypatch, outcome
    ):
        """NON-VACUITY. An event emitted unconditionally would count nothing."""
        events = self._capture(monkeypatch, outcome)
        assert [e["type"] for e in events] == ["pin_marker_write"]


class TestRegistration:

    @pytest.fixture
    def config(self):
        return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

    def _commands(self, entries):
        out = []
        for entry in entries:
            for hook in entry.get("hooks", []):
                out.append(hook)
        return out

    def test_registered_on_both_routes(self, config):
        ups = self._commands(config["hooks"]["UserPromptSubmit"])
        assert any("pin_marker_writer.py" in h["command"] for h in ups)

        post = config["hooks"]["PostToolUse"]
        skill_groups = [g for g in post if g.get("matcher") == "Skill"]
        assert len(skill_groups) == 1
        assert any(
            "pin_marker_writer.py" in h["command"]
            for h in skill_groups[0]["hooks"]
        )

    def test_both_registrations_are_async(self, config):
        """async is the STRUCTURAL half of the non-denial guard, measured with
        a control: the same script registered sync and exiting 2 blocks the
        prompt; registered async it does not, while its sentinel proves it ran.
        """
        found = 0
        for event in ("UserPromptSubmit", "PostToolUse"):
            for hook in self._commands(config["hooks"][event]):
                if "pin_marker_writer.py" in hook["command"]:
                    found += 1
                    assert hook.get("async") is True, (
                        f"the {event} registration is not async"
                    )
        assert found == 2

    def test_user_prompt_entry_is_appended_after_the_existing_three(self, config):
        """An entry inserted between the bootstrap writer and the prompt gate
        breaks a pinned order assertion elsewhere in the suite.
        """
        commands = [h["command"] for h in
                    self._commands(config["hooks"]["UserPromptSubmit"])]
        index = next(i for i, c in enumerate(commands) if "pin_marker_writer.py" in c)
        writer = next(i for i, c in enumerate(commands) if "bootstrap_marker_writer.py" in c)
        gate = next(i for i, c in enumerate(commands) if "bootstrap_prompt_gate.py" in c)
        assert writer < gate
        assert index > gate
        assert index == len(commands) - 1

    def test_the_registered_script_exists(self, config):
        assert HOOK_SCRIPT.is_file()


# --------------------------------------------------------------------------
# Non-goal
# --------------------------------------------------------------------------

def test_no_reader_is_wired_to_the_markers():
    """This change ships NO reader. Wiring the existing pinned-section parser
    to these markers moves the extent contract into this change, which is the
    coupling the staged delivery exists to prevent.
    """
    staleness_source = (HOOKS_DIR / "staleness.py").read_text(encoding="utf-8")
    assert "PINNED_START_MARKER" not in staleness_source
    assert "pin_markers" not in staleness_source
