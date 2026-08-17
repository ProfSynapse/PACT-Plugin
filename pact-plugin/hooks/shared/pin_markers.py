#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/shared/pin_markers.py

Summary: Pure planner for the declared `## Pinned Context` marker PAIR. Decides
WHERE the two markers go and WHETHER they go in at all, composes the new file
content, and certifies that the composition expelled nothing. No I/O, no
filesystem, no hook frame, no exceptions.

A PAIR, EMITTED IN ONE COMPOSITION. Both marker lines go in together or neither
does. The state space is therefore four -- neither, both in order, both
inverted, exactly one -- and the ladder in `plan_insertion` names all four.

THE PAIR AND THE MARKER-AWARE WRITER ARE ONE UNIT, and that is the safety
argument rather than a preference. An END marker with a marker-BLIND pin writer
CREATES a gap it did not have before: the writer anchors on the heading, appends
at the end of the section, and lands the new pin BELOW the END marker where no
cap measures it. Measured at a cap of 12 with a 13th pin appended -- no markers
DENIES, a pair with the insertion INSIDE DENIES, a pair with an append BELOW the
END is ALLOWED. So `commands/pin-memory.md` must place new pins above the END
marker, and this module is only half of that story.

THAT HALF IS AN INSTRUCTION, NOT A MECHANISM, and the asymmetry is deliberate
rather than unfinished. No code path in this repository inserts a pin -- the
command file instructs an LLM to make the edit, and the caps gate only judges
the resulting Edit. So nothing here can enforce the placement, and a test that
composes the document the way the instruction says is a second opinion about
the instruction rather than evidence that it was obeyed. Tracked as issue
#1358, with the reason a caps-gate refusal was deferred rather than omitted.

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
INSERTION: two literals are spliced in at two computed offsets and no existing
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
    MEMORY_END_MARKER,
    MEMORY_START_MARKER,
    PACT_BOUNDARY_PREFIXES,
    PINNED_END_MARKER,
    PINNED_START_MARKER,
    SESSION_BOUNDARY_PREFIX,
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
#
# THE SESSION PREFIX IS INERT HERE TODAY, AND IT IS PRESENT FOR SYMMETRY WITH
# `staleness._parse_pinned_section`, WHICH NEEDS IT. MEASURED: the caller
# below narrows its window to the MEMORY region before it searches, and it
# REFUSES with `SkipReason.NO_MEMORY_REGION` when that marker pair is absent,
# so no session marker can enter the window this pattern scans. The sibling
# takes the MANAGED region and does reach one. Do NOT read this term as
# evidence that a route to it was found here. If the narrowing above is ever
# widened, this term is what stops the same defect arriving in this file.
_BOUNDARY_ALT = "|".join(PACT_BOUNDARY_PREFIXES)
_PINNED_TERMINATOR = re.compile(
    rf'(?:#{{1,2}}\s|<!-- (?:{_BOUNDARY_ALT}|{SESSION_BOUNDARY_PREFIX}))'
)

# The pinned section heading. `re.search` takes the FIRST occurrence and a
# second one is ignored, which matches every existing reader of this region.
_PINNED_HEADING = re.compile(r'^## Pinned Context\s*\n', re.MULTILINE)

# The literal lines that get spliced in. The trailing newline is part of each
# unit: the certificate below is stated over these LINES, not over the bare
# markers, so a marker and its newline can never be accounted separately.
START_LINE = PINNED_START_MARKER + "\n"
END_LINE = PINNED_END_MARKER + "\n"


def _narrow_to_memory_region(
    region_text: str, region_start: int
) -> tuple[str, int] | None:
    """Narrow an already-extracted managed region to the MEMORY region inside
    it, or None when the memory marker pair is not there.

    THE WINDOW AND THE TARGET MUST BE THE SAME REGION, and before this function
    they were not. `extract_managed_region` returns the WIDE region, and the
    `## Pinned Context` heading this module anchors on is defined to live in the
    NARROW memory region nested inside it. The session block sits inside the
    wide window and ABOVE the narrow one, so a heading placed there is the FIRST
    match and the anchor lands on it. Neither downstream guard stops that:
    `certify_expel_nothing` declines placement in its own docstring, and the
    collision label answers a different question. Placement had ONE runtime
    constraint and this is now the other half of it.

    BOTH BOUNDARIES ARE MARKER LINES, THROUGH THE FILE'S SINGLE DEFINITION.
    `marker_line_span` decides what counts, so this function adds no third
    reading of `the marker occupies a line`.

    WHAT THAT GUARANTEES, AND AGAINST WHAT. The managed region holds the
    session block ABOVE the memory markers, and the session block interpolates
    caller-influenced values. A value carrying the marker TEXT cannot move
    either boundary, because the value lands inside a longer line and such a
    line does not strip to the marker.

    THE CONTROL THAT GUARANTEE RESTS ON IS IN ANOTHER MODULE, AND IT IS NAMED
    HERE BECAUSE THIS FUNCTION CANNOT SEE IT. A value that could occupy a line
    ALONE would move the boundary, and what stops that is
    `session_resume._sanitize_prompt_field`, which substitutes control
    characters. MEASURED at that function: `'/tmp/x\\n<marker>\\ny'` comes back
    as `'/tmp/x <marker> y'`, so the newline goes and THE MARKER TEXT SURVIVES.
    That survival is why a text search was defeated and a line rule is not. If
    that sanitize stops covering newlines, this boundary is reachable again.

    WHAT THIS DOES NOT GUARANTEE: a marker line placed BY HAND in the managed
    region above the genuine one. That is a user editing a block the file
    labels do-not-edit, which is the same self-inflicted population as a
    hand-deleted marker pair.

    THE PREVIOUS VERSION OF THIS PARAGRAPH ARGUED THE WRONG CASE, and the error
    is worth keeping because it is easy to repeat. It said a marker OUTSIDE the
    managed block belongs to no boundary this writer honours, and that taking
    the caller's already-bounded text made a forgery unrepresentable. THAT IS
    TRUE ABOUT OUTSIDE AND THE ATTACK IS INSIDE, where a forgery was fully
    representable and unguarded. The sentence certified a property the function
    did not have, and it read as covering all cases because it named none.

    THE SEARCH IS BOUNDED TO THE MANAGED REGION IT IS GIVEN, never to the whole
    file. That remains correct and is now the SECOND bound rather than the only
    one.

    RETURNS ABSOLUTE OFFSETS, matching `extract_managed_region`, so the caller
    substitutes the pair and every offset arithmetic below it is unchanged.

    THE PAIR IS REQUIRED, AND THE MISSING-PAIR CASE REFUSES rather than falls
    back to the wide window. See `SkipReason.NO_MEMORY_REGION` for why a
    fall-back is unsafe on this document shape.

    DO NOT WIDEN THIS WINDOW TO AGREE WITH THE READER. The pin reader,
    `staleness._parse_pinned_section`, resolves a LOOSER window than this one,
    and the difference is deliberate at each of the three points below. THE TWO
    DIRECTIONS ARE NOT THE SAME SIZE OF MISTAKE. Widening this function back to
    the managed region reopens the placement defect the narrow window closes, so
    that direction is a defect. Narrowing the READER is a possible future change
    with an unmeasured blast radius, so that direction is open work rather than a
    tidying pass. Neither gap is closed here, and an editor who finds the two
    windows inconsistent must leave them inconsistent.

    THE READER TAKES ITS SEARCH START FROM A BARE SUBSTRING SEARCH FOR
    `MEMORY_START_MARKER`, where this function needs a marker LINE. So the marker
    text carried INSIDE a longer session line moves the reader search start and
    does not move this window. NO CODE AT EITHER SITE HOLDS THAT CLOSED. What
    holds it closed is the newline substitution in
    `session_resume._sanitize_prompt_field`, which is recorded at that one site,
    so a change there separates the two starts with no signal at either function.

    THE TWO END BOUNDARIES AGREE TODAY, AND NO LINE OF CODE STATES THE
    AGREEMENT. `MEMORY_END_MARKER` carries the `PACT_MEMORY_` prefix, and the
    reader terminator alternation is built from `PACT_BOUNDARY_PREFIXES`, so the
    reader stops at that marker BY PREFIX MEMBERSHIP and not by naming it. A
    READER OF THE CODE SEES NO END BOUND AND A DRIVER OF A DOCUMENT SEES ONE.
    Drive a document before you conclude the two ends differ.

    THE READER REACHES THAT MARKER ONLY WHEN NOTHING STOPS IT EARLIER. A heading
    or a boundary comment between the pinned body and the marker ends the reader
    scan at that earlier line, and the canonical template puts a `## Working
    Memory` heading in that position. So on a template-made document the reader
    does not reach the marker, and a rename of it changes nothing there. DO NOT
    READ THAT AS PERMISSION TO MOVE THE MARKER OUT OF THE PREFIX FAMILY. A
    document with no such heading between the pins and the marker DOES reach it,
    a user edit can make one, and the pin cap gate compares two user documents.
    On that document the rename removes the reader bound with nothing to see,
    and this function is unchanged in each case.

    A MISSING MARKER PAIR SPLITS THE TWO IN KIND RATHER THAN IN WIDTH. This
    function returns None and plans nothing. The reader keeps its search start at
    0 and continues across the full managed region. Do not make this function
    fall back to reach that behaviour.

    THE STRIPPED COMPARISON IS INHERITED FROM `marker_line_span` AND WAS
    RE-JUDGED FOR THIS JOB, because that docstring justifies its tolerance by a
    REFUSAL failure direction and this site bounds a WINDOW instead. MEASURED
    on an indented memory start marker: `marker_line_span` accepts the line and
    `_find_terminator_offset`, which matches the RAW line, does not. THE
    DISAGREEMENT DOES NOT REACH THE PLANNER, because the two bound DIFFERENT
    spans -- this one sets the window, and the terminator scan runs INSIDE the
    window it produced, so the marker line is excluded before that scan sees
    it. A raw comparison here would refuse an indented but faithful document,
    which is the over-block direction this repository treats as the worse
    fault.
    """
    start_span = marker_line_span(region_text, MEMORY_START_MARKER)
    if start_span is None:
        return None
    # The END of the marker line, so the window begins on the NEXT line and
    # `region_start` stays a line start for every offset computed below it.
    inner_start = start_span[1]
    tail = region_text[inner_start:]
    end_span = marker_line_span(tail, MEMORY_END_MARKER)
    if end_span is None:
        return None
    return tail[:end_span[0]], region_start + inner_start


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


def is_line_start(text: str, offset: int) -> bool:
    """True when `offset` begins a line of `text`.

    THE PROPERTY THIS NAMES WAS PREVIOUSLY UNNAMED, AND THAT IS THE WHOLE
    REASON THE FUNCTION EXISTS. Every insertion offset this module produces
    happens to be a line start: the START offset is a `re.MULTILINE` heading
    match, and the END offset is a terminator line start by construction of
    `_find_terminator_offset`. Nothing stated that, no test asserted it, and no
    docstring mentioned it -- so it held as an accident of the bytes.

    An accident is not reviewable. It has no site to inspect and no failure
    mode to enumerate, and it stops holding silently the moment a computation
    upstream of it changes. This module already shipped one guard of exactly
    that shape past five instruments, three reviewers and two certifiers. A
    PAIR adds a SECOND offset under the same property, so the accident is now
    load-bearing twice over. Naming it costs one function.

    WHY IT MATTERS FOR THE COMPOSITION. If an offset falls mid-line, the splice
    cuts a user's line in two and leaves a mangled fragment on either side of
    the marker. The certificate cannot see that: the composition is still
    byte-preserving, the length arithmetic still holds, and the unbounded
    replace still reproduces the original. Byte preservation and textual sanity
    are different claims, and only the first was ever proven.

    OFFSET 0 IS A LINE START BY DEFINITION, AND IT IS HANDLED FIRST FOR A
    MEASURED REASON. Written as a bare `text[offset - 1] == "\\n"`, offset 0
    reads `text[-1]` -- the LAST character of the file. Measured: on `'abc\\n'`
    that returns True for entirely the wrong reason, and on `'abcX'` it returns
    False. Neither raises. A guard that answers confidently and wrongly at its
    own boundary is worse than no guard.
    """
    if offset <= 0:
        return offset == 0
    if offset > len(text):
        return False
    return text[offset - 1] == "\n"


def marker_line_span(text: str, literal: str) -> tuple[int, int] | None:
    """Span of the first line of `text` that IS `literal`, else None.

    THE SINGLE DEFINITION OF `the marker occupies a line`. `marker_line_offset`
    below is this function's start projection and `marker_line_present` is its
    boolean shadow. Keeping ONE implementation is what stops a document being
    marked by one reading and unmarked by another -- the exact drift that a
    second, independently-written predicate produced here once already.

    RETURNS BOTH ENDS, and the second one is why this function exists rather
    than the offset alone. A caller that needs the text AFTER the marker line
    cannot get there from the start offset without computing the line length,
    and computing it separately is that second predicate again. Returning the
    span keeps the terminator rule inside the one walk that owns it.

    `splitlines()` is deliberate: it splits on LF, CRLF and CR alike, so the
    property is stated once and holds for every terminator rather than
    enumerating them. `keepends=True` is what makes the END offset carry the
    same rule -- a `find("\\n")` beside this walk would disagree with it on a
    bare-CR document, which is the drift this docstring exists to prevent.

    THE COMPARISON IS STRIPPED, AND HERE THAT IS THE SAFE DIRECTION -- unlike
    `staleness._find_declared_end_offset`, which tolerates trailing whitespace
    ONLY. The two look alike and must not be unified. This predicate decides
    whether to REFUSE a write, so over-matching costs a skipped write and is
    fail-safe. That one decides where a cap stops counting, so over-matching
    drops a pin out of the counted span and fails OPEN. Tolerance follows the
    direction of failure, never the resemblance of the code.

    ONE CALLER USES THIS TO BOUND A WINDOW RATHER THAN TO REFUSE, and the
    tolerance was re-judged for that job rather than inherited. See
    `_narrow_to_memory_region`, which records the measurement.
    """
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.strip() == literal:
            return offset, offset + len(line)
        offset += len(line)
    return None


def marker_line_offset(text: str, literal: str) -> int | None:
    """Offset of the first line of `text` that IS `literal`, else None.

    THE START PROJECTION of `marker_line_span`, and a projection rather than a
    second walk on purpose: two walks are the twin that drifts, which this
    file has paid for once already at this exact predicate.
    """
    span = marker_line_span(text, literal)
    return None if span is None else span[0]


def _is_end_marked(region_text: str, body_end: int) -> bool:
    """Return True iff the END marker occupies the line THIS WRITER EMITS IT ON.

    THE POSITIONAL TWIN OF `_is_already_marked`, and it is positional for the
    identical reason: a predicate defined over where a copy MIGHT appear has a
    residual exactly the width of its own enumeration, while a predicate
    matching the writer's own output shape has none by construction.

    `body_end` is the terminator offset that closes the pinned body. On a
    document this writer has already marked, the forward scan STOPS AT the END
    marker itself -- the literal carries the `PACT_MEMORY_` prefix, so it is a
    scan terminator -- which is why the same offset identifies the marker line
    on a written document and the insertion point on an unwritten one.

    The comparison is stripped, matching the START sibling. See
    `marker_line_offset` for why that is the safe direction HERE and the unsafe
    one in `staleness._find_declared_end_offset`.
    """
    tail = region_text[body_end:]
    if not tail:
        return False
    return tail.splitlines()[0].strip() == PINNED_END_MARKER


def marker_line_present(text: str, literal: str) -> bool:
    """True when `literal` OCCUPIES A LINE anywhere in `text`, under ANY line
    terminator.

    WHY THIS EXISTS AS A NAMED PREDICATE RATHER THAN A SIDE EFFECT. The guard
    that stopped a second marker being written was never implemented. It was
    EMERGENT: `certify_expel_nothing` strips `START_LINE`, so a document that
    already carried `marker + LF` made the unbounded replace remove two copies
    and the equality fail. That is a byte accident of an unrelated comparison,
    and it stops working the moment the bytes differ -- on a CRLF document the
    existing copy is `marker + CRLF`, the replace does not reach it, and the
    write proceeds onto a document that already has one.

    AN EMERGENT GUARD BREAKS SILENTLY WHEN THE BYTES CHANGE, because nothing
    names the property it was protecting. This function names it.

    THE PROPERTY IS `the marker occupies a line`, not `the marker is followed
    by one specific byte sequence`. `splitlines()` supplies that directly: it
    splits on LF, CRLF and CR alike, so the predicate is stated once and holds
    for every terminator rather than enumerating them. The same call at
    `_is_already_marked` is why that sibling was CRLF-safe all along while this
    property was not.

    `.strip()` MATCHES THE SIBLING DELIBERATELY. A whitespace-padded marker
    line is a marker line by any reading, and the argument for it is set out in
    `_is_already_marked` above. Keeping the two predicates on the same footing
    is what stops a document being marked by one reading and unmarked by the
    other.

    A MID-LINE MENTION IS CORRECTLY EXCLUDED, and that is load-bearing rather
    than incidental. A line reading `prose naming the <marker> inline` does not
    strip to the marker, so prose that merely discusses the marker is not a
    collision. Widening this to a bare substring test would resurrect exactly
    the over-broad predicate this module removed.

    THE LITERAL IS AN ARGUMENT RATHER THAN A CONSTANT, so the pair gets one
    predicate instead of two. A second copy specialised to the END marker would
    be the twin that drifts.
    """
    return marker_line_offset(text, literal) is not None


@dataclass(frozen=True)
class Insertion:
    """Where the two marker lines go, as absolute offsets into the FULL file.

    TWO offsets and TWO literals, and the ORDER BETWEEN THEM IS A REAL STATE
    THAT CAN BE WRONG. That is a gain, not a cost: crossed offsets duplicate
    bytes, so the certificate's length assertion catches them. With a single
    splice point no choice of offset could drop a byte, which meant NO offset
    was rejectable and placement was constrained by tests alone. The pair gives
    the certificate its offset power back.

    BOTH OFFSETS MUST BE LINE STARTS. The certificate enforces it through
    `is_line_start`; read that function for why the property is named here
    rather than left to hold by accident.

    Carries the literals but NOT the new content. The writer composes the new
    content through `apply_insertion`, so exactly one site in the codebase
    assembles these bytes and the certificate can wrap that one site.
    """

    start_offset: int   # start of the `## Pinned Context` heading line
    end_offset: int     # start of the terminator line that ends the body
    start_line: str
    end_line: str


class SkipReason(str, Enum):
    """Why no insertion happened. Journalled, so a later reader can tell WHICH
    precondition refused rather than only that nothing occurred.

    `plan_insertion` returns one of these instead of None for that reason: a
    bare None collapses the distinct outcomes into one and makes a test unable
    to assert the ladder step that was reached.

    `INVERTED_PAIR` AND `UNPAIRED` ARE BACK, and the round trip is worth one
    sentence because it is a lesson about enum hygiene rather than churn. They
    were deleted when the END marker was removed, correctly: both describe
    states that only a two-marker pair can occupy, and with one marker the
    state space was exactly two -- present or absent. The pair restores the
    states, so it restores the members. Deleting them rather than commenting
    them out is what made this restoration a clean re-add instead of an
    archaeology exercise.
    """

    NOT_MIGRATED = "noop_not_migrated"
    # The managed region is there and the MEMORY marker pair inside it is not,
    # so the window this writer anchors in does not exist. REFUSE rather than
    # widen back to the managed region.
    #
    # WHY A FALL-BACK IS UNSAFE HERE, and it is a property of the build order
    # rather than a preference. The emitter writes the managed marker, the
    # title, THEN the session block, THEN the memory marker, so the session
    # block sits ABOVE the memory marker BY CONSTRUCTION. Removing the memory
    # markers does not remove the session block. A document missing the pair
    # therefore STILL HOLDS A POSITION where a heading can sit above the pinned
    # section, which is the placement this narrowing exists to close. Widening
    # on exactly that document restores the defect on the one shape that has it.
    #
    # EMITTING THE MISSING PAIR IS ALSO REFUSED, and for a different cause: it
    # would write markers back into a block the file labels do-not-edit, on a
    # gitignored file with no recovery commit.
    #
    # THE POPULATION IS ONE ROUTE. Every emitter writes the two markers
    # unconditionally, and the two constants entered the tree in one commit, so
    # no shipped version wrote the outer marker without the inner pair. The only
    # route to this state is a hand-edit, and it does not self-clear, because
    # the migration returns early when the managed marker is present and it is
    # the only path that adds the memory markers to an existing document.
    #
    # RESIDUAL, STATED RATHER THAN IMPLIED: this narrowing does not cover a
    # heading a user places BY HAND inside the session block, which is the same
    # self-inflicted population as the marker-less document itself.
    NO_MEMORY_REGION = "noop_no_memory_region"
    NO_SECTION = "noop_no_section"
    EMPTY_SECTION = "noop_empty_section"
    # The pinned body contains a fenced code block. See `_body_contains_a_fence`.
    FENCED_BODY = "noop_fenced_body"
    ALREADY_MARKED = "already_marked"
    # Both markers occupy lines, but the END sits ABOVE the START. The document
    # is marked, and marked WRONGLY. This writer will not repair it: moving or
    # deleting an existing marker mutates existing bytes, which the pure-
    # insertion shape excludes and the certificate cannot cover. Reported so a
    # reader can tell a wrong pair from a missing one.
    INVERTED_PAIR = "inverted_pair"
    # Exactly ONE of the two markers occupies a line. Skip rather than complete
    # the pair, for the same reason: this writer emits both lines in ONE
    # composition or none. Adding the missing half would be a repair, and a
    # repair is a shape the certificate was never written to prove.
    #
    # NOT AN ERROR STATE. A START with no END is exactly what a reader must
    # tolerate, and `staleness._parse_pinned_section` does tolerate it by
    # falling through to the inferred scan.
    UNPAIRED = "unpaired"
    # A document carrying a marker on its OWN LINE, or at the END of a line,
    # somewhere other than the position this writer emits -- so the certificate
    # refused the write. NARROWER THAN `contains the marker anywhere`: a
    # MID-LINE copy passes the certificate, the write proceeds, and no
    # collision is reported. That is the correct outcome and it means this
    # count UNDERCOUNTS documents that merely mention the marker.
    #
    # Split out of ALREADY_MARKED, which reported it under a SUCCESS-shaped
    # label -- a refused migration and a completed one were the same journal
    # entry, so the collision was unobservable.
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
    1b. The MEMORY marker pair sits inside that managed region, and the search
       narrows to it. THE WINDOW AND THE TARGET MUST BE ONE REGION: the pinned
       heading is defined to live in the memory region, while the managed region
       also contains the session block ABOVE it, so a wider window matches a
       heading there FIRST. Absent pair REFUSES; see
       `SkipReason.NO_MEMORY_REGION` for why widening is unsafe on that exact
       shape, and `_narrow_to_memory_region` for the bound on the search.
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

    THE FENCE BLINDNESS IS LEFT EXACTLY AS FOUND, and that is a separate claim
    from "no reader is changed", which this paragraph used to make and which is
    now false -- `staleness._parse_pinned_section` reads `PINNED_END_MARKER`.
    What is unchanged is `_find_terminator_offset`, which every consumer of this
    region shares. Repairing its fence blindness would be an extent-contract
    change: on a currently-truncated pinned region a more complete reader RAISES
    the observed pin count, which can cross a count threshold and produce an
    over-block introduced BY the repair. So this planner refuses the shapes it
    cannot read safely rather than teaching the scanner to read them.

    IDEMPOTENCE IS A POSITIONAL PAIR CHECK. The state space is four, and the
    ladder names all four: neither marker in the writer's own positions (write),
    both (already marked), exactly one (unpaired), and both present somewhere
    with the END above the START (inverted). Ordering and pairing are real
    questions again, because there are two things to order and two to pair.

    A FILE CARRYING ONE MARKER AND NOT THE OTHER IS HALF-MARKED. It is not an
    error and nothing here raises on it, but it is not the finished shape
    either, and it must not be reported as one. Readers must tolerate it: a
    START with no END parses exactly as an unmarked file does.

    This function never repairs a boundary: moving or deleting an existing
    marker mutates existing bytes, which the pure-insertion shape excludes and
    the certificate cannot cover.
    """
    try:
        region = extract_managed_region(content)
        if region is None:
            return SkipReason.NOT_MIGRATED
        region_text, region_start = region

        # NARROW THE WINDOW TO THE REGION THE TARGET IS DEFINED TO LIVE IN.
        # Everything below this line reads `region_text` as its coordinate
        # system, so substituting the pair here is what moves the anchor search
        # off the session block. See `_narrow_to_memory_region`.
        inner = _narrow_to_memory_region(region_text, region_start)
        if inner is None:
            return SkipReason.NO_MEMORY_REGION
        region_text, region_start = inner

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
        # gives it. The writer's OWN shape is checked first, by adjacency --
        # see `_is_already_marked` for why that is not a whole-file search.
        # THE PAIR LADDER IS POSITIONAL, NOT A WHOLE-FILE SEARCH, and that
        # distinction is the whole reason this ladder is shaped as it is.
        #
        # A whole-file search for either marker is the predicate this module
        # ALREADY REMOVED once. It blocks the write forever on any document
        # that happens to carry a copy anywhere -- the "carrier in the gap"
        # defect -- and it hides a stray copy under a skip instead of routing
        # it to the certificate, which is what makes a collision countable.
        # Restoring the pair must not restore that.
        #
        # So both halves are judged by POSITION, against the two places this
        # writer emits: the START on the line above the pinned heading, the END
        # on the terminator line that closes the body. A copy anywhere else is
        # NOT this writer's output, and it must fall through to the certificate.
        start_marked = _is_already_marked(region_text, heading.start())
        end_marked = _is_end_marked(region_text, rel_end)
        if start_marked and end_marked:
            return SkipReason.ALREADY_MARKED
        if start_marked or end_marked:
            # HALF-MARKED, and it gets its own label rather than the
            # success-shaped one. Reporting `already_marked` here would file a
            # document that still needs its other half under the outcome that
            # means "nothing to do" -- the same shape that once hid a marker
            # collision inside a completed-migration count. This writer emits
            # both lines in ONE composition, so it will not complete the pair
            # either: adding the missing half is a repair, and the certificate
            # was never written to prove a repair.
            return SkipReason.UNPAIRED

        # AN INVERTED PAIR IS NAMED HERE rather than left to the certificate,
        # because it asks a different question from a collision. A collision is
        # a stray copy the writer must not duplicate. An inversion is a pair
        # that is already complete and already WRONG, and no write can improve
        # it. Whole-file, but reached only when BOTH markers occupy lines -- so
        # a single stray copy still falls through to the certificate and stays
        # countable.
        start_at = marker_line_offset(content, PINNED_START_MARKER)
        end_at = marker_line_offset(content, PINNED_END_MARKER)
        if start_at is not None and end_at is not None and end_at < start_at:
            return SkipReason.INVERTED_PAIR

        # BOTH offsets are line starts, and neither is a coincidence:
        #   START -- `heading.start()` is a `re.MULTILINE` match, so it sits
        #            immediately after a newline.
        #   END   -- `_find_terminator_offset` walks line by line, so every
        #            offset it returns begins a line.
        # `rel_end` bounded the body for the emptiness and fence checks above;
        # it is now ALSO the end offset, because this write declares both
        # boundaries in one composition rather than only where the region
        # begins. The certificate re-checks the line-start property rather than
        # trusting these two sentences.
        return Insertion(
            start_offset=region_start + heading.start(),
            end_offset=region_start + rel_end,
            start_line=START_LINE,
            end_line=END_LINE,
        )
    except Exception:  # noqa: BLE001 -- totality guard; see SkipReason.PLAN_FAILED
        return SkipReason.PLAN_FAILED


def apply_insertion(content: str, ins: Insertion) -> str:
    """Compose the new content. The ONLY site that assembles these bytes.

    The marker line goes ABOVE the `## Pinned Context` heading, on its own line,
    so the heading and its body stay exactly where they already sit. One splice
    at one point: nothing is read between offsets, and nothing is rewritten.

    THE CERTIFICATE GUARDS THIS FUNCTION, and with a PAIR it guards more of it
    than it could before. Two splice points CAN cross: if `end_offset` precedes
    `start_offset`, the middle slice runs backwards, comes back empty, and the
    tail is emitted twice -- so the length assertion catches it. While there was
    one splice point no offset was rejectable at all, and placement rested on
    tests alone.

    A defect in `_is_already_marked` remains a different matter: the certificate
    cannot see it, and the four-pass count is what covers it.
    """
    return (
        content[:ins.start_offset]
        + ins.start_line
        + content[ins.start_offset:ins.end_offset]
        + ins.end_line
        + content[ins.end_offset:]
    )


def certify_expel_nothing(old: str, new: str, ins: Insertion) -> bool:
    """Return True iff `new` is `old` plus exactly the one marker line.

    THIS IS A REFUSAL, NOT A TEST. The writer runs it before the write and
    skips the write when it returns False, so a composition that cannot be
    proven byte-identical never reaches the disk. Failure is the safe
    direction.

    SCOPE, AND IT IS NARROWER THAN THE NAME SUGGESTS. THIS CERTIFIES TWO
    STRINGS, NOT A FILE. The writer obtains `old` from `Path.read_text`, which
    performs universal-newline translation: a CRLF document arrives here
    already converted to LF, and the composition is written back byte-faithful.
    So a pin command on a CRLF file rewrites every line ending in it, and BOTH
    ARGUMENTS HERE ARE ALREADY NORMALISED BEFORE THE COMPARISON BEGINS -- this
    function cannot see that change and never could.

    That conversion is NOT introduced by this module. Measured at the revision
    this work branched from: every existing writer of the file pairs the same
    normalising read with a byte-faithful write, and two of them were driven
    end to end against a CRLF file and converted it. The conversion is
    inherited; what is new is a function named for a guarantee. STATE THE
    SCOPE RATHER THAN WEAKEN THE GUARANTEE: this proves nothing was expelled
    FROM THE TEXT IT WAS GIVEN, and it is not a byte-level guarantee about the
    file on disk.

    Two assertions, and the second is not redundant with the first:

    - the length grew by exactly the marker line, which catches a dropped or
      duplicated byte anywhere in the STRING -- see the scope note above, which
      is why this does not say `in the file`;
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
      certificate is not vacuous -- it guards `apply_insertion`, which is the
      only place a COMPOSITION defect can enter.

      IT DOES NOT GUARD THE DETECTOR. `_is_already_marked` is a SECOND logic
      site -- it slices the gap, selects the last line and compares it stripped
      -- and a defect there causes re-insertion or permanent suppression,
      NEITHER of which this function can observe. It only ever inspects a
      composition it was handed; it never asks whether that composition should
      have been produced. THE FOUR-PASS COUNT IS WHAT COVERS THAT. See the
      complementarity note below for the exact division.

      The qualifier `COMPOSITION` is doing real work and is not padding. This
      sentence once read `the only place a defect can enter`, which was true
      when the detector was a one-line substring search and which the adjacency
      change falsified by ADDING A SECOND SITE. Unqualified, it also
      CONTRADICTED the complementarity note twelve lines below -- that note
      says a mid-line quote is caught by `_is_already_marked` and only by it,
      and a sole guard is by definition a place a defect can enter. Restoring
      the missing word makes the sentence true again rather than deleting a
      claim that was right about its own subject.
    - CAUGHT: the marker literal already present in `old` on its OWN line, or
      at the END of a line. Both put a `marker + newline` in `old`, so the
      unbounded replace strips two occurrences, the equality fails, and the
      write is refused.

    THE DETECTOR AND THIS CERTIFICATE ARE COMPLEMENTARY, NOT OVERLAPPING, AND
    THE DIVISION IS EXACT. Stated for these two mechanisms by name, because it
    is the sentence a future reader is most likely to delete as redundant
    defence-in-depth:

      - A MID-LINE quote is caught by NEITHER MECHANISM, and it needs no guard.
        Measured in both: `_is_already_marked` compares a STRIPPED line against
        the marker, and a line reading `I wrote <marker> in my notes` does not
        strip to it; this certificate then passes too, because `old` holds no
        `marker + newline` at all. The write proceeds and the certificate
        returns True.

        THAT IS THE CORRECT OUTCOME, not a hole. A mid-line literal is invisible
        to EVERY line-anchored reader of this region, so it is not a boundary
        for anything and there is nothing for a guard to protect. ADD NO GUARD
        HERE: one would have to match a bare substring, which is precisely the
        over-broad predicate this module removed.

        THIS SENTENCE PREVIOUSLY CLAIMED `_is_already_marked` CAUGHT IT, AND
        ONLY IT. That was false when written -- an adjacency predicate cannot
        match a mid-line quote at any position. The claim is worth correcting
        rather than deleting because it named a guard that does not fire, and a
        reader auditing this module would have gone looking for it.
      - An OWN-LINE quote is caught by THIS CERTIFICATE AND ONLY BY IT. The
        adjacency detector does not match it -- an own-line copy anywhere other
        than immediately above the pinned heading is not the shape the writer
        emits -- so the plan proceeds and this is the only remaining guard.

    SO THE DIVISION IS: own-line copies away from the writer's own position are
    this certificate's alone, and mid-line copies belong to nobody because they
    are not boundaries. Removing this certificate on the ground that the
    detector covers own-line copies opens a hole with a named shape.

    A NOTE ON WHAT THIS PARAGRAPH REPLACED, because the error is instructive.
    It used to say the collision was `refused EARLIER, by the presence check in
    plan_insertion`. THAT WAS TRUE WHEN WRITTEN AND WAS FALSIFIED BY THE
    DETECTOR CHANGE -- under the whole-file substring search the planner did
    refuse first, and under the adjacency predicate an own-line quote falls
    through to here. The change that falsified it edited a different function
    four hundred lines away and never touched this line, so no diff review
    could surface it. WHEN YOU CHANGE THE DETECTOR, RE-READ THIS WHOLE
    DOCSTRING -- not this paragraph.

    The scope of that instruction is not a detail. It first read `re-read
    this`, meaning this note, and the very next claim it failed to catch sat
    four hundred words ABOVE it in this same docstring: `the only place a
    defect can enter`, which the detector change had falsified in exactly the
    way this note describes. A REMEDY WHOSE SCOPE IS NARROWER THAN THE HAZARD
    REPRODUCES THE HAZARD, and this one demonstrated it inside one docstring
    within minutes of being written.

    Returns False rather than raising on any anomaly, including a non-`str`
    argument: every failure of this function must land on the refuse side.
    """
    try:
        # THE LINE-START GATE, FIRST, because it is the only clause here that
        # judges PLACEMENT rather than bytes. A mid-line offset splits a user's
        # line and strands a fragment, and every clause below would still pass:
        # the composition is byte-preserving, the arithmetic holds, and the
        # replace reproduces `old`. Byte preservation and textual sanity are
        # different claims and only the first was ever proven here.
        #
        # MEASURED, so the gate is not theoretical: both offsets are line starts
        # on a well-formed document, but on a document whose managed END marker
        # is NOT preceded by a newline the END offset is mid-line. The property
        # is therefore real and NOT universal, which is exactly the case for
        # checking it rather than asserting it in a comment.
        #
        # This REFUSES rather than raises, like every other clause.
        if not is_line_start(old, ins.start_offset):
            return False
        if not is_line_start(old, ins.end_offset):
            return False
        if len(new) != len(old) + len(ins.start_line) + len(ins.end_line):
            return False
        if new.replace(ins.start_line, "").replace(ins.end_line, "") != old:
            return False
        # BOTH markers are tested, not just the START. An `old` that already
        # carries the END on a line of its own is just as much a document this
        # writer must not add a second copy to.
        #
        # THE COLLISION CLAUSE IS EXPLICIT BECAUSE IT USED TO BE AN ACCIDENT.
        # The two checks above are a pure composition proof and they are
        # SATISFIED by a document that already carries a marker: nothing is
        # expelled, one line is added, and the arithmetic holds. Such a document
        # was refused only because the unbounded replace ABOVE happened to strip
        # two copies when both ended LF -- a property of the bytes, not of the
        # rule. On CRLF the existing copy ends `\r\n`, the replace never reaches
        # it, and the composition certified cleanly onto a document that already
        # had one. `marker_line_present` is terminator-agnostic, so the refusal
        # now follows from the property rather than from the encoding.
        return not (
            marker_line_present(old, PINNED_START_MARKER)
            or marker_line_present(old, PINNED_END_MARKER)
        )
    except Exception:  # noqa: BLE001 -- a certificate must refuse, never raise
        return False
