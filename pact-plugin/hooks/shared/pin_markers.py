#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/shared/pin_markers.py

Summary: Pure planner for the declared `## Pinned Context` marker pair. Decides
WHERE the two markers go and WHETHER they go in at all, composes the new file
content, and certifies that the composition expelled nothing. No I/O, no
filesystem, no hook frame, no exceptions.

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
rebuild cannot satisfy: see `certify_expel_nothing`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from shared.claude_md_manager import (
    PACT_BOUNDARY_PREFIXES,
    PINNED_END_MARKER,
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
# real cycle, so their success is a result rather than a silent no-op. A
# re-export is safe because `from shared.claude_md_manager import ...` binds a
# SUBMODULE, and Python resolves that without requiring the parent package's
# `__init__` to have finished executing.
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

# The literal lines that get spliced in. The trailing newline is part of the
# unit: the certificate below is stated over these LINES, not over the bare
# markers, so a marker and its newline can never be accounted separately.
START_LINE = PINNED_START_MARKER + "\n"
END_LINE = PINNED_END_MARKER + "\n"


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


@dataclass(frozen=True)
class Insertion:
    """Where the two marker lines go, in absolute offsets into the FULL file.

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
    bare None collapses six distinct outcomes into one and makes a test unable
    to assert the ladder step that was reached.
    """

    NOT_MIGRATED = "noop_not_migrated"
    NO_SECTION = "noop_no_section"
    EMPTY_SECTION = "noop_empty_section"
    # The pinned body contains a fenced code block. See `_body_contains_a_fence`.
    FENCED_BODY = "noop_fenced_body"
    ALREADY_MARKED = "already_marked"
    INVERTED_PAIR = "inverted_pair"
    UNPAIRED = "unpaired"
    # Totality guard. The six above enumerate every DESIGNED outcome; this one
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

    1. The file carries a PACT-managed region. A file migration has not
       processed is REFUSED, because migration re-emits the three memory
       sections in canonical order and can therefore emit an end marker before
       a start marker on a file whose sections currently sit in another order.
       Refusing here is the cheap remedy; the alternative changes migration
       itself. It costs no coverage, and costs none STRUCTURALLY rather than by
       luck: migration emits the `## Pinned Context` heading and the managed
       marker by the same mechanism, so no file can carry the heading without
       the marker.
    2. A `## Pinned Context` heading exists inside that region. Most files do
       not have one. Placing a pair there would mean CREATING the section,
       which is an insert above pre-existing content and is exactly the
       destructive shape this write is forbidden to perform.
    3. The pinned body is non-empty. An empty section reads as ABSENT to the
       only current reader of this region, which returns None for it, so a pair
       around it would declare a boundary that no consumer believes in. Such a
       section is a migration-emitted heading with nothing under it, so no-op
       here skips a heading the plugin itself wrote, never a user's content.
    4. The measured body contains NO fenced-code marker. The terminator scan is
       not fence aware, so on a fenced body the offset it returns cannot be
       trusted and the write refuses rather than guesses. See
       `_body_contains_a_fence` for why the predicate is a bare substring test
       and why nothing cleverer is safe.
    5. Both markers are absent.

    NO READER IS CHANGED BY ANY OF THIS. The fence-blindness lives in
    `_find_terminator_offset`, which every existing consumer of this region
    shares, and repairing it there would be an extent-contract change: on a
    currently-truncated pinned region a more complete reader RAISES the
    observed pin count, which can cross a count threshold and produce an
    over-block introduced BY the repair. So this planner refuses the shapes it
    cannot read safely and leaves the reader exactly as it found it.

    IDEMPOTENCE IS AN ORDERED CHECK, NOT A PRESENCE CHECK. A presence-only test
    reports an INVERTED pair as correct, and the second write then adds nothing
    -- silently, in the direction that looks like success. So the start marker
    must be found BEFORE the end marker, and every other combination is a
    reported no-op. This function never repairs a boundary: moving or deleting
    an existing marker mutates existing bytes, which the pure-insertion shape
    excludes and the certificate cannot cover.
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
        # gives it. On an already-marked file the checks above all pass -- the
        # end marker matches the terminator alternation, so the body measured
        # here is the real body and is non-empty -- and this branch reports
        # `already_marked`. The order only changes WHICH no-op reason is
        # journalled in states that combine a marker with a missing region or
        # section, and every one of those outcomes is a no-op either way.
        #
        # Decided on the WHOLE file with first-find on each literal, matching
        # `extract_managed_region`.
        start_at = content.find(PINNED_START_MARKER)
        end_at = content.find(PINNED_END_MARKER)
        if start_at != -1 and end_at != -1:
            return (
                SkipReason.ALREADY_MARKED if start_at < end_at
                else SkipReason.INVERTED_PAIR
            )
        if start_at != -1 or end_at != -1:
            return SkipReason.UNPAIRED

        # `heading.end() > heading.start()` and the terminator is found at or
        # after `body_from`, so the start offset is always below the end one.
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

    The start marker line goes ABOVE the `## Pinned Context` heading and the end
    marker line goes on its own line immediately above the terminator, so the
    pair wraps the heading and the body where they already sit. Nothing between
    the two offsets is read, and nothing outside them is touched.

    The body may end in blank lines. The end offset stays the terminator line's
    start, so the end marker lands after those blank lines and they survive.
    """
    return (
        content[:ins.start_offset]
        + ins.start_line
        + content[ins.start_offset:ins.end_offset]
        + ins.end_line
        + content[ins.end_offset:]
    )


def certify_expel_nothing(old: str, new: str, ins: Insertion) -> bool:
    """Return True iff `new` is `old` plus exactly the two marker lines.

    THIS IS A REFUSAL, NOT A TEST. The writer runs it before the write and
    skips the write when it returns False, so a composition that cannot be
    proven byte-identical never reaches the disk. Failure is the safe
    direction.

    Two assertions, and the second is not redundant with the first:

    - the length grew by exactly the two lines, which catches a dropped or
      duplicated byte anywhere in the file;
    - removing every occurrence of both lines from `new` reproduces `old`
      exactly, which catches a byte that moved without the length changing.

    THE `.replace` IS DELIBERATELY UNBOUNDED. If `old` quotes one of these
    marker literals in the user's own prose, an unbounded replace strips that
    occurrence from `new` while the one in `old` remains, the equality fails,
    and the write is refused. A count-limited replace would mask exactly that
    case. This guard therefore needs no census of how often such prose occurs.

    WHAT THIS DOES AND DOES NOT CERTIFY -- measured, not reasoned, because the
    honest scope is narrower than the word "certificate" suggests:

    - CAUGHT: offsets that cross, or an end offset pulled back before its
      start. Those splice over the bytes between the two points and DROP them,
      and the length arm refuses. This is the reachable failure: it is a bug in
      the planner or in a future edit to `apply_insertion`, and it is precisely
      the class that silently destroys user content.
    - CAUGHT when driven directly: a marker literal already present in `old`.
      In the assembled write this is refused EARLIER, by the ordered-pair check
      in `plan_insertion`, which sees the stray literal and returns `unpaired`.
      The two mechanisms are independent on purpose -- this one does not depend
      on the planner being correct -- so neither may be removed on the ground
      that the other covers it.
    - NOT CAUGHT: any well-ordered offset pair. Splicing the two lines at
      offsets 5 and 6, or at 0 and end-of-file, passes both assertions. THIS
      CERTIFICATE PROVES THAT NOTHING WAS EXPELLED. IT DOES NOT PROVE THE
      MARKERS LANDED IN THE RIGHT PLACE. Placement is a separate property and
      is pinned by tests that assert what sits on either side of each marker.

    Returns False rather than raising on any anomaly, including a non-`str`
    argument: every failure of this function must land on the refuse side.
    """
    try:
        if len(new) != len(old) + len(ins.start_line) + len(ins.end_line):
            return False
        return new.replace(ins.start_line, "").replace(ins.end_line, "") == old
    except Exception:  # noqa: BLE001 -- a certificate must refuse, never raise
        return False
