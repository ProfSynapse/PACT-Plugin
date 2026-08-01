#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/shared/pin_markers.py

Summary: Pure planner for the declared `## Pinned Context` START marker. Decides
WHERE the marker goes and WHETHER it goes in at all, composes the new file
content, and certifies that the composition expelled nothing. No I/O, no
filesystem, no hook frame, no exceptions.

ONE MARKER, NOT A PAIR. There is no declared END, and its absence is the
intended state rather than a half-finished pair -- see `claude_md_manager` at
the constant for the measured reason. Everything here is written for a single
insertion point: one offset, one literal, and a presence check rather than an
ordering check.

Used by: `hooks/pin_marker_writer.py`, which owns every side effect -- stdin,
path resolution, the file lock, the atomic write and the journal. That split is
not tidiness. The pinned-region cap this feature leads to is a TWO-STATE
predicate: it compares a pre-edit parse against a post-edit parse and refuses
only when the post state is strictly worse. A two-state predicate cannot be
certified by single-document probes at any probe count, so a region change has
to be certified on DOCUMENT PAIRS. Keeping the planner pure lets a test drive
whole documents through one function and compare before against after, with no
hook process and no disk. Folding these three functions into the hook script
would satisfy every other constraint on this feature and still lose that.

THE SHAPE OF THE WRITE IS THE SAFETY ARGUMENT. The insertion is PURE OFFSET
INSERTION: one literal is spliced in at one computed offset and no existing
byte is parsed, rewritten, reordered or dropped. The alternative shape -- parse
the region into entries and rebuild the text from them -- silently deletes
whatever it does not recognise, and the target file is gitignored and
unrecoverable. Pure insertion also supports a MECHANICAL certificate, which a
rebuild cannot satisfy: see `certify_expel_nothing`, and read its scope note
before trusting it to cover placement, because it does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from shared.claude_md_manager import (
    PACT_BOUNDARY_PREFIXES,
    PINNED_START_MARKER,
    extract_managed_region,
)
# The line scanner is REUSED from the module that owns it rather than copied.
# Re-implementing its dozen lines here would make this the second definition of
# "where does a section end", and the two would drift apart exactly when the
# terminator rule changes -- which is the failure this whole feature exists to
# close. `shared/__init__.py` already imports from a sibling top-level hook
# module (`pin_caps`), so the direction of this import is established.
#
# WHY NO CYCLE. `staleness` does import from this package, so the ground is not
# that the dependency runs one way -- it does not. A cycle needs something this
# module imports, directly or transitively, to import THIS module back, and
# nothing does.
#
# MEASURED in an isolated copy of the hooks tree, because two earlier attempts
# to state this ground were wrong in opposite directions and a guess here costs
# something real -- an unverified warning would deter a legitimate change:
#
#   - re-exporting `pin_markers` from `shared/__init__.py`, APPENDED: imports fine
#   - the same re-export as the FIRST import after `__future__`:      imports fine
#   - CONTROL, `claude_md_manager` importing `pin_markers` back:      ImportError,
#     "cannot import name ... from partially initialized module"
#
# The control is what makes the two clean arms readable: the harness CAN detect a
# real cycle, so their success is a result rather than a silent no-op.
#
# THE MECHANISM, also measured rather than reasoned: `from
# shared.claude_md_manager import ...` resolves a SUBMODULE, and a submodule
# import needs only the parent package present in `sys.modules` with its
# `__path__` set. Probed from inside a partially-executed `shared/__init__.py`:
# `"shared" in sys.modules` is True and `__path__` is already bound there, so a
# half-initialised package still resolves its own submodules.
#
# So the condition to avoid is not a re-export. It is a module in this import
# chain -- `claude_md_manager` or `staleness` -- importing `pin_markers`.
from staleness import _find_terminator_offset

# The scan terminator for the pinned body. Built from PACT_BOUNDARY_PREFIXES so
# a fourth prefix added there is picked up here by a one-line constant change,
# and MIRRORS the pattern `staleness._parse_pinned_section` compiles inline: an
# H1 or H2 heading, or any PACT-managed boundary comment. Spelling the three
# prefixes literally here would be a twin copy that drifts silently.
_BOUNDARY_ALT = "|".join(PACT_BOUNDARY_PREFIXES)
_PINNED_TERMINATOR = re.compile(rf'(?:#{{1,2}}\s|<!-- (?:{_BOUNDARY_ALT}))')

# The pinned section heading. `re.search` takes the FIRST occurrence and a
# second one is ignored, which matches every existing reader of this region.
_PINNED_HEADING = re.compile(r'^## Pinned Context\s*\n', re.MULTILINE)

# The literal line that gets spliced in. The trailing newline is part of the
# unit: the certificate below is stated over this LINE, not over the bare
# marker, so the marker and its newline can never be accounted separately.
START_LINE = PINNED_START_MARKER + "\n"


def _body_contains_a_fence(body: str) -> bool:
    """Return True when the pinned body contains ANY fenced-code marker.

    THE PREDICATE IS DELIBERATELY CRUDE, AND THAT IS THE WHOLE DESIGN. It is a
    substring test. It has NO fence grammar: it does not pair openers with
    closers, does not track nesting, does not care about line position, and
    does not compute where a fence begins or ends. It CAN over-refuse. It
    CANNOT misplace a marker.

    WHY NOTHING CLEVERER IS SAFE HERE. `_find_terminator_offset` has no fence
    awareness, and the guarantee it relies on -- that the managed region holds
    only plugin-generated content -- is FALSE for the pinned section, where
    pins are user-authored. So a terminator-shaped line inside a user's fenced
    snippet stops the scan early and the marker lands inside their code block.

    The obvious repair is a backtick tracker that finds the first terminator
    OUTSIDE a fence, with a refusal gate for the ambiguous cases. MEASURED, it
    fails on two real shapes: a four-backtick fence wrapping a three-backtick
    one, and a tilde fence containing a heading-shaped line. Both are misplaced.
    AND THE REFUSAL GATE CANNOT SAVE IT, because the gate asks the SAME tracker
    whether the landing line sits inside a fence. On both shapes the tracker
    believes it does not, so the gate stays silent at exactly the point it is
    needed. CHECK AND ACT SHARE ONE HANDLE, AND THE HANDLE IS BROKEN. A guard
    that consults the mechanism it is guarding cannot catch that mechanism
    failing.

    That is why the only safe predicate is one that needs no grammar at all.

    COST, named rather than hidden: this refuses on real files whose pinned
    bodies merely quote code, including one 12-pin file in the measured corpus.
    That is a DEFERRAL, not a loss -- a file with pins and no markers is an
    expected state that the consumer of these markers must already handle, and
    a later change shipping a real fence handler can narrow this predicate.
    """
    return "```" in body or "~~~" in body


def _is_already_marked(region_text: str, heading_start: int) -> bool:
    """Return True iff this document carries the marker THIS WRITER EMITTED.

    THE PRINCIPLE IS `ACCEPT ONLY WHAT THE WRITER EMITS`, and it is the third
    predicate tried. The first two were defined by where a stray copy of the
    marker might APPEAR, and each was defeated by one appearing somewhere the
    predicate was not looking -- line-anchored scored 3 of 7, region-bounded 2
    of 7, the two combined were measured insufficient, and a gap-wide variant
    scored 7 of 7 while still admitting a false positive.

    The reframe that ends the sequence: `apply_insertion`'s output space is a
    SINGLETON. It can emit exactly one shape -- the marker alone on the line
    immediately above the first pinned heading, inside the managed region. A
    predicate matching that shape has no residual BY CONSTRUCTION, whereas any
    predicate defined over where a copy might appear has a residual exactly the
    width of its own enumeration. Every failed candidate was asymmetric with
    the writer, and the residual was that asymmetry.

    WHY THE COMPARISON IS STRIPPED RATHER THAN BYTE-EXACT. Measured 6 of 6
    against byte-exact's 3 of 6: byte-exact fails on a trailing space, a
    trailing tab and a leading indent, and a cost arm placed a carrier in all
    three arms without either variant producing a false positive. A
    whitespace-padded marker line IS a marker line by any reading, so
    byte-exact treating it as ABSENT is itself an asymmetry -- the same defect
    class one layer in. `.strip()` also subsumes an `alone on the line`
    requirement without a second clause: a line reading `text <marker>` strips
    to itself and is correctly refused.

    WHAT A WRONG ANSWER HERE COSTS, because it is worse than the defect being
    fixed. If this stops recognising the writer's own marker, every pin command
    re-inserts one. Two routes reach that, and they are NOT equally bounded:

      - WHITESPACE DRIFT under a byte-exact predicate is BOUNDED AT 2 and
        self-halting, because the re-inserted marker is clean and the next pass
        matches it. Measured over ten passes: the count reaches 2 and stays.
      - A GENUINELY BROKEN GAP COMPUTATION -- wrong region, wrong heading, an
        off-by-one -- is UNBOUNDED. The re-inserted marker still does not
        match, so nothing halts.

    The four-passes-yield-one-marker test catches both, since even the bounded
    case violates `exactly one`. Both are tested by name, because from outside
    they look identical and only one of them stops.

    ADJACENCY HOLDS UNDER BOTH MACHINE WRITERS, and this was MEASURED before
    the predicate was written rather than assumed after. The Retrieved Context
    writer rebuilds the span ABOVE this marker and the Working Memory writer
    the span below, and a carrier was really placed by each -- so the
    measurement is not vacuous. The load-bearing detail is that the rebuild
    always emits a TRAILING BLANK LINE before the next section, which is the
    sole reason a machine-placed carrier cannot occupy the adjacent line. That
    blank is asserted by test; if it ever goes, this predicate degrades
    silently.
    """
    gap_lines = region_text[:heading_start].splitlines()
    if not gap_lines:
        return False
    return gap_lines[-1].strip() == PINNED_START_MARKER


@dataclass(frozen=True)
class Insertion:
    """Where the marker line goes, as an absolute offset into the FULL file.

    ONE offset and ONE literal. There is no end-side pair, so there is also no
    ordering between two offsets to get wrong -- and, as the certificate's
    scope note records, no offset the certificate can reject either.

    Carries the literal but NOT the new content. The writer composes the new
    content through `apply_insertion`, so exactly one site in the codebase
    assembles these bytes and the certificate can wrap that one site.
    """

    start_offset: int   # start of the `## Pinned Context` heading line
    start_line: str


class SkipReason(str, Enum):
    """Why no insertion happened. Journalled, so a later reader can tell WHICH
    precondition refused rather than only that nothing occurred.

    `plan_insertion` returns one of these instead of None for that reason: a
    bare None collapses the distinct outcomes into one and makes a test unable
    to assert the ladder step that was reached.

    THERE IS NO `inverted_pair` AND NO `unpaired`, and their absence is
    deliberate. Both described states that only a two-marker pair can occupy.
    With one marker the state space is exactly two -- present or absent -- so
    those members became unreachable, and an unreachable enum member is the
    dead reference a later reader takes as live. They were deleted rather than
    kept behind a comment: unreachable is fine, silently unreachable is not,
    and a deleted member cannot be misread while a commented one relies on the
    comment being read.
    """

    NOT_MIGRATED = "noop_not_migrated"
    NO_SECTION = "noop_no_section"
    EMPTY_SECTION = "noop_empty_section"
    # The pinned body contains a fenced code block. See `_body_contains_a_fence`.
    FENCED_BODY = "noop_fenced_body"
    ALREADY_MARKED = "already_marked"
    # A document that CONTAINS the marker somewhere, but not in the position
    # this writer emits, and whose write was therefore refused by the
    # certificate. Split out of ALREADY_MARKED, which reported it under a
    # SUCCESS-shaped label -- a refused migration and a completed one were the
    # same journal entry, so the collision was unobservable.
    #
    # THIS IS RESTORED OBSERVABILITY, NOT A NEW FEATURE, and the history is the
    # reason it is worth an enum member. `unpaired` and `inverted_pair` were
    # deleted as unreachable. They were unreachable for a PAIR reason -- one
    # marker cannot be unpaired or inverted -- but the CONDITION they reported,
    # a document carrying the marker in a shape the writer did not make, did
    # not vanish with the pair. It migrated into the success label. A signal
    # removed as dead code was the only observability for a live hazard, and
    # this is the second time in this arc that has happened.
    MARKER_COLLISION = "noop_marker_collision"
    # Totality guard. The five above enumerate every DESIGNED outcome; this one
    # exists so the function can promise it never raises without that promise
    # depending on a saturated type. Every operation in `plan_insertion` is a
    # string or regex operation on a `str` and none of them can raise for a
    # `str` input, so this is near-unreachable -- but near-unreachable is not
    # unrepresentable, and a caller that hands in a non-`str` must get a refusal
    # rather than a traceback out of a hook that is forbidden to fail.
    PLAN_FAILED = "error_plan_failed"


def plan_insertion(content: str) -> Insertion | SkipReason:
    """Decide what to insert, or why not. Pure. Never raises.

    The precondition order is load-bearing and is checked in this sequence:

    1. The file carries a PACT-managed region. This is REQUIRED MECHANICALLY,
       not merely prudent: the region is the coordinate system the offset is
       expressed in, and a file migration has not processed supplies none. Its
       coverage cost is zero STRUCTURALLY rather than by luck, because
       migration emits the `## Pinned Context` heading and the managed marker
       by the same mechanism, so no file can carry the heading without the
       marker.

       NOTE FOR ANYONE REVISITING THIS STEP: it once carried a second
       justification -- that migration re-emits sections in canonical order and
       could therefore emit an END marker before a START marker, inverting a
       byte-correct pair. That reason RETIRED WITH THE PAIR. One marker cannot
       be inverted. The step survives on the mechanical ground alone, which is
       sufficient on its own.
    2. A `## Pinned Context` heading exists inside that region. Most files do
       not have one. Placing a marker there would mean CREATING the section,
       which is an insert above pre-existing content and is exactly the
       destructive shape this write is forbidden to perform.
    3. The pinned body is non-empty. An empty section reads as ABSENT to the
       only current reader of this region, which returns None for it, so a
       boundary declared around it is one no consumer believes in. Such a
       section is a migration-emitted heading with nothing under it, so no-op
       here skips a heading the plugin itself wrote, never a user's content.
    4. The measured body contains NO fenced-code marker. The terminator scan is
       not fence aware, so on a fenced body the extent it reports cannot be
       trusted and the write refuses rather than guesses. See
       `_body_contains_a_fence` for why the predicate is a bare substring test
       and why nothing cleverer is safe.
    5. The marker is absent.

    NO READER IS CHANGED BY ANY OF THIS. The fence-blindness lives in
    `_find_terminator_offset`, which every existing consumer of this region
    shares, and repairing it there would be an extent-contract change: on a
    currently-truncated pinned region a more complete reader RAISES the
    observed pin count, which can cross a count threshold and produce an
    over-block introduced BY the repair. So this planner refuses the shapes it
    cannot read safely and leaves the reader exactly as it found it.

    IDEMPOTENCE IS A PRESENCE CHECK, AND FOR ONE MARKER THAT IS THE WHOLE OF
    IT. The state space is exactly two: the marker is in the file, or it is
    not. Absent, the write runs. Present, the file is already marked and the
    write is a no-op. There is no third state to name, because ordering needs
    two things to order and pairing needs two things to pair.

    A FILE CARRYING THIS MARKER AND NO CLOSING ONE IS CORRECT, NOT BROKEN. That
    is the intended shipped shape. Nothing here may treat a missing end marker
    as an error, an incomplete write, or a repair opportunity -- there is no
    end marker to miss.

    This function never repairs a boundary: moving or deleting an existing
    marker mutates existing bytes, which the pure-insertion shape excludes and
    the certificate cannot cover.
    """
    try:
        region = extract_managed_region(content)
        if region is None:
            return SkipReason.NOT_MIGRATED
        region_text, region_start = region

        heading = _PINNED_HEADING.search(region_text)
        if heading is None:
            return SkipReason.NO_SECTION

        body_from = heading.end()
        rel_end = _find_terminator_offset(
            region_text, body_from, _PINNED_TERMINATOR
        )
        body = region_text[body_from:rel_end]
        if not body.strip():
            return SkipReason.EMPTY_SECTION

        # A fenced body is refused outright. The terminator scan is not fence
        # aware, so the offset computed for such a body cannot be trusted.
        # See `_body_contains_a_fence` for why this is a substring test and
        # not a fence parser.
        if _body_contains_a_fence(body):
            return SkipReason.FENCED_BODY

        # The marker state is checked LAST, in the ladder position the design
        # gives it. See `_is_already_marked` for why this is an ADJACENCY test
        # and not the whole-file substring search it replaced.
        if _is_already_marked(region_text, heading.start()):
            return SkipReason.ALREADY_MARKED

        # The offset is the start of the heading line, so the marker lands on
        # its own line immediately above it. `rel_end` above bounded the body
        # for the emptiness and fence checks; it is deliberately NOT used as an
        # offset, because this write declares where the region BEGINS and takes
        # no position on where it ends.
        return Insertion(
            start_offset=region_start + heading.start(),
            start_line=START_LINE,
        )
    except Exception:  # noqa: BLE001 -- totality guard; see SkipReason.PLAN_FAILED
        return SkipReason.PLAN_FAILED


def apply_insertion(content: str, ins: Insertion) -> str:
    """Compose the new content. The ONLY site that assembles these bytes.

    The marker line goes ABOVE the `## Pinned Context` heading, on its own line,
    so the heading and its body stay exactly where they already sit. One splice
    at one point: nothing is read between offsets, and nothing is rewritten.

    THIS IS THE FUNCTION THE CERTIFICATE ACTUALLY GUARDS. With a single splice
    point no offset can drop bytes, so a defect here can no longer come from
    choosing the wrong place -- it can only come from mis-assembling the pieces.
    Any edit to this expression is therefore the thing to certify, and the
    certificate's mutation arm exists to prove it can still catch one.
    """
    return (
        content[:ins.start_offset]
        + ins.start_line
        + content[ins.start_offset:]
    )


def certify_expel_nothing(old: str, new: str, ins: Insertion) -> bool:
    """Return True iff `new` is `old` plus exactly the one marker line.

    THIS IS A REFUSAL, NOT A TEST. The writer runs it before the write and
    skips the write when it returns False, so a composition that cannot be
    proven byte-identical never reaches the disk. Failure is the safe
    direction.

    Two assertions, and the second is not redundant with the first:

    - the length grew by exactly the marker line, which catches a dropped or
      duplicated byte anywhere in the file;
    - removing every occurrence of that line from `new` reproduces `old`
      exactly, which catches a byte that moved without the length changing.

    THE `.replace` IS DELIBERATELY UNBOUNDED, AND ITS REACH IS NARROWER THAN
    THIS DOCSTRING USED TO CLAIM. It replaces the marker line -- marker PLUS
    NEWLINE -- not the marker. So it catches a quote only when that quote is
    itself followed by a newline. MEASURED, on the three shapes a document can
    quote the marker in:

        marker alone on its own line   -> REFUSED
        marker at the end of a line    -> REFUSED
        marker in the MIDDLE of a line -> PASSES

    The mid-line case passes because `old` then contains no `marker + newline`
    at all, so the single inserted occurrence is removed cleanly and the
    equality holds. THE EARLIER CLAIM THAT THIS INDEPENDENTLY CATCHES `a
    document quoting the literal` WAS FALSE FOR THAT SHAPE, and it was false
    when written rather than broken later.

    Passing the mid-line case is the correct outcome, not a residual hole: a
    marker in the middle of a line is not a boundary, the write proceeds
    normally, and the next pass reports the document as already marked. What
    was wrong was the claim's SCOPE, not the behaviour.

    ITS SCOPE NARROWED WHEN THE SECOND MARKER WENT, AND THE NARROWING IS
    MEASURED RATHER THAN ARGUED. Run at EVERY offset from 0 to len(old), on
    documents of several shapes, the certificate returned True in every single
    case -- 160 offsets on a realistic file, and every offset of an empty
    string, a newlines-only string and a near-miss prefix.

    - NOT CAUGHT: ANY offset whatsoever. A single splice point cannot cross
      itself, so no choice of offset can drop a byte. Splicing the marker at
      offset 5, or 0, or end-of-file, passes both assertions.
      **THIS CERTIFICATE PROVES BYTE PRESERVATION OF THE ASSEMBLY. IT DOES NOT
      PROVE THE MARKER LANDED IN THE RIGHT PLACE, AND IT DOES NOT EVEN PROVE
      THE OFFSET IS SANE.** A reader who knows only that it "certifies the
      write" will assume placement is covered. That assumption was survivable
      when a second offset existed to be crossed. It is not survivable now.
      Placement is constrained by tests, and by NOTHING ELSE.
    - CAUGHT: a mis-assembled composition. Dropping a byte, duplicating one,
      inserting the marker twice, omitting the newline and reordering the tail
      are each refused, with a correct assembly accepted as the control. So the
      certificate is not vacuous -- it guards `apply_insertion`, which is now
      the only place a defect can enter.
    - CAUGHT when driven directly: the marker literal already present in `old`.
      In the assembled write that document is refused EARLIER, by the presence
      check in `plan_insertion`. The two mechanisms are independent on purpose
      -- this one does not depend on the planner being correct -- so neither
      may be removed on the ground that the other covers it.

    Returns False rather than raising on any anomaly, including a non-`str`
    argument: every failure of this function must land on the refuse side.
    """
    try:
        if len(new) != len(old) + len(ins.start_line):
            return False
        return new.replace(ins.start_line, "") == old
    except Exception:  # noqa: BLE001 -- a certificate must refuse, never raise
        return False
