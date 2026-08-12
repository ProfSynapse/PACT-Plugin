#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/pin_staleness_gate.py
Summary: PreToolUse marker-gate that denies Edit/Write on the project
         CLAUDE.md's Pinned Context section when a stale-pins-pending
         marker is present in the session directory.
Used by: hooks.json PreToolUse with matcher \"Edit|Write\"

Phase F defense-in-depth backstop for #492. The SessionStart
additionalContext directive (session_init.py step 4b) is the primary
enforcement; this hook is the secondary guard that fires at the moment
of the Edit/Write call rather than relying on the orchestrator honoring
the directive.

Gate triggers only when ALL hold:
  1. Tool is Edit or Write (enforced by hooks.json matcher)
  2. Target file path resolves to the project CLAUDE.md
  3. The edit reaches the Pinned Context section, WHERE THAT SECTION
     RESOLVES. STATE THE FALLBACK WHENEVER THIS CONDITION IS QUOTED,
     because a locus claimed with no fallback is the same defect in a
     new position: it leads a maintainer to believe the unbounded
     shapes are closed, and they are not.
       WRITE, and any comparison of two whole documents: the locus is
       the Pinned Context section when BOTH SIDES resolve one. If
       either side does not, the comparison FALLS BACK to the shipped
       selection, which is the managed region when both sides carry
       the markers and the whole text when they do not.
       EDIT: the locus is the offset of `old_string` in the file on
       disk, tested against the pinned span. A fragment wholly outside
       that span does not reach the section and the gate stays quiet.
       NO `## Pinned Context` HEADING AT ALL: there is no span, so
       this condition does not bound the document. See
       `_counts_show_an_add` for what that costs and why it is
       irreducible here.
  4. Stale-pins-pending marker exists in session_dir
  5. Not a teammate session (teammates bypass; CLAUDE.md edits are scoped to the team-lead session)

SACROSANCT (post-load runtime): every raisable path after module load is
wrapped in try/except that defaults to allow (exit 0 with suppressOutput).
A gate-logic bug must never block a tool call. Fail-open: missing
session_dir, unparseable CLAUDE.md, unresolvable marker → allow.
Module LOAD failure is the deliberate exception: a failed import would
otherwise crash the hook (exit 1 = platform-non-blocking = silent
fail-open), so it denies via _emit_load_failure_deny instead.

Input: JSON from stdin with tool_name, tool_input, session_id, etc.
Output: JSON with hookSpecificOutput.permissionDecision (deny case)
        or {\"suppressOutput\": true} (allow / passthrough)
"""

from __future__ import annotations

# ─── stdlib first (used by _emit_load_failure_deny BEFORE wrapped imports) ─
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

_SUPPRESS_OUTPUT = json.dumps({"suppressOutput": True})


def _emit_load_failure_deny(stage: str, error: BaseException) -> NoReturn:
    """Stdlib-only fail-closed deny for module-load failure. Mirrors the
    ``dispatch_gate`` / ``bootstrap_gate`` analogue.

    Without this, a raise from the cross-package imports below would crash the
    hook (exit 1), which the platform treats as a NON-blocking PreToolUse hook
    — the Edit/Write tool would PROCEED and the staleness gate would silently
    FAIL-OPEN. Emitting a deny + exit 2 keeps the gate fail-CLOSED.
    hookEventName MUST be present.
    """
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"PACT pin_staleness_gate {stage} failure — blocking for safety. "
                f"{type(error).__name__}: {error}. Check hook installation "
                "and shared module availability."
            ),
        }
    }))
    print(
        f"Hook load error (pin_staleness_gate / {stage}): {error}",
        file=sys.stderr,
    )
    sys.exit(2)


# ─── fail-closed wrapper on cross-package imports ──────────────────────────
try:
    import shared.pact_context as pact_context
    from shared import match_project_claude_md
    from pin_caps import parse_pins
except BaseException as _module_load_error:  # noqa: BLE001 — fail-closed catch-all
    _emit_load_failure_deny("module imports", _module_load_error)

# Marker file name written when stale-pins-pending state is detected.
# Placed in session_dir so it is per-session scoped — clears on new
# session, cannot persist across /clear (session_dir is rebuilt per session).
#
# 🔴 THIS MODULE IS READ ONLY ON THIS MARKER, AND THAT IS A CONSTRAINT RATHER
# THAN A PREFERENCE. The gate tests whether the marker is present. It must
# never create it, and it must never remove it. IF A REFUSAL REMOVED ITS OWN
# TRIGGER, the trap would disappear by DELETING THE EVIDENCE OF IT rather than
# by repair: the next add would be allowed for the wrong cause, and every arm
# over this gate would go green while that happened. A coder can close the trap
# by accident that way, which is why the prohibition is written at the name
# rather than left implied.
#
# WHERE THE LIFECYCLE LIVES TODAY: `session_init.check_pin_stale_block_directive`
# writes it and removes it, at SessionStart only.
#
# A NAME COLLISION THAT TRAPS A SEARCH, RECORDED BECAUSE IT WAS CHECKED RATHER
# THAN ASSUMED. `pin_marker_writer.py` is registered on `UserPromptSubmit` AND
# on `PostToolUse` with the matcher `Skill`, so it READS like a mid-session
# manager of this signal. IT IS NOT ONE. It carries zero references to this
# constant and it serves the pin command, whose `## Pinned Context` marker pair
# is a different object that shares a naming family. A reader who greps for the
# hook that manages this marker finds that file first, and it is the wrong file.
PIN_STALENESS_MARKER_NAME = "pin-staleness-pending"

# 🔴 THE COMMAND NAMED HERE MUST BE THE COMMAND THAT ARCHIVES, AND FOR A TIME
# IT WAS NOT. This text named `/PACT:pin-memory`, which does not archive: it
# ADDS a pin and it points the user at `/PACT:prune-memory` for removal. So a
# user who OBEYED this refusal arrived at a command that cannot clear the
# condition, and stayed denied. THAT IS THE TRAP THIS GATE EXISTS TO PREVENT,
# reached through the MESSAGE rather than through the predicate, which is why
# it survived every arm aimed at the predicate.
# BEFORE YOU EDIT THIS STRING, OPEN THE COMMAND FILE AND CONFIRM THE COMMAND
# ARCHIVES. The deny text is not evidence about its own subject.
#
# AND IT PROMISES NO ORDER. An earlier wording said to archive BEFORE editing,
# which the gate could not deliver: the marker was created and removed at
# SessionStart only, so a user who obeyed was denied for the rest of the
# session. `track_files.clear_pin_staleness_marker_if_resolved` now clears the
# marker when the signal clears, on a hand edit and on the archive command, so
# the sentence below is a statement about a mechanism that is available rather
# than a promise.
_DENY_REASON = (
    "Pinned Context edits are gated: stale pins detected. "
    "Run /PACT:prune-memory to archive the stale pins. "
    "PACT re-checks the pins after that command runs, so the archive "
    "clears this gate inside the same session."
)

_GATED_TOOLS = frozenset({"Edit", "Write"})


# A heading a memory writer emits. `working_memory.py` builds each one as
# `f"### {date_str}"` with `date_str = now.strftime("%Y-%m-%d %H:%M")`, so the
# shipped shape is a date and a time.
#
# THIS PATTERN HAS THREE PRODUCERS AND ONLY TWO OF THEM ARE WRITERS. Recorded
# here because a reader who sees one writer proposes to derive this pattern
# from that writer's format, and the count is what refuses it:
#   1. `working_memory.py`, a machine writer, emits a date AND a time.
#   2. The retrieved-entry writer, a machine writer, reaches the same region.
#   3. A HUMAN, who hand-writes an entry and is bound by no format at all.
#   And a fourth ROUTE that is not a writer: a memory-record FIELD VALUE can
#   carry a heading into the managed region, so a title can arrive with no
#   author who intended a title.
# AN EMITTER SAYS WHAT TO PRODUCE. AN ACCEPTOR SAYS WHAT TO ADMIT. They are
# different jobs, and the acceptor must admit what every producer emits.
#
# THE PATTERN WAS WRITTEN BY READING THE WRITERS. IT IS NOT COMPUTED FROM THEM,
# AND IT MUST NOT BE. Do not replace it with a pattern built from the writer's
# `strftime` format. That derivation is refused on three causes, each one
# sufficient alone:
#   CAUSE 1, IT NARROWS THE ACCEPTOR TO ONE PRODUCER. The writers emit a date
#     AND a time, so a derived pattern has a REQUIRED time and REFUSES
#     `### 2026-08-05`. That heading is then counted as a PIN, a memory write
#     that adds one reads as a pin add, and the gate DENIES a faithful edit.
#     The cost is cardinal and it is measured, not predicted.
#   CAUSE 2, THE ALPHABET RELOCATES RATHER THAN VANISHES. A derivation needs a
#     DIRECTIVE MAP from `strftime` directives to fragments, and an EXPRESSION
#     TRACER, because the writer holds no literal title format: it builds
#     `f"### {date_str}"` at one site and `date_str` at another. One alphabet
#     becomes two.
#   CAUSE 3, THE COUPLING HAS NO PRECEDENT. No shipped hook imports below the
#     memory skill package. A count of zero is evidence of a convention and
#     not proof of a rule, so the coupling is priced as new. Where a hook and
#     that package need one behaviour, this repository ships two copies and a
#     drift gate, and that is the house answer rather than a workaround.
#
# WHAT SURVIVES THE REFUSAL, STATED BECAUSE IT RUNS AGAINST IT. A tolerance
# list is an author-written alphabet, and a later widening can be ABSORBED by
# adding a line to it. That is a maintenance hazard and it is real. It is NOT
# removed by deriving: a DIRECTIVE MAP IS ITSELF A LIST, so the absorption
# moves one layer down and returns as an AUTHOR CHOICE at the unknown-directive
# arm, raise-and-fail-open or fall-back-and-widen. Smaller, and not absent.
#
# EACH TOLERANCE BELOW CARRIES ITS REASON AT ITS SITE, so a later widening
# cannot arrive as a bare line with no argument attached to it.
# 🔴 A REASON PER TOLERANCE REDUCES THE ABSORPTION. IT DOES NOT BAR IT. A
# future editor can write a reason too, and a plausible reason beside a wrong
# line reads as more considered than a bare line, not less. This is the
# residual, stated rather than closed.
#
# THE ARM THAT HOLDS THIS IS IN `tests/test_working_memory.py`, WITH THE
# WRITERS, because a person who edits a writer does not read the tests of this
# gate. IT PINS A RELATION RATHER THAN A FORMAT, AND THE DIFFERENCE IS
# LOAD-BEARING: an arm pinning only the emitted format would redden when a
# WRITER moves and stay GREEN when THIS pattern moves, so tightening the
# pattern here would break the pair with a passing arm over it. Do not replace
# that arm with a format assertion.
#
# VERBOSE MODE IS WHAT PUTS EACH REASON AT ITS SITE. It changes no accepted
# string here: the pattern carries no literal space, so the whitespace that
# verbose mode discards does not occur in it, and the marker is escaped
# because an unescaped `#` would start a comment.
_DATE_LED_HEADING_RE = re.compile(
    r"""
    ^\#\#\#                # The marker. NO TOLERANCE: a heading at another
                           # depth is a different structural thing, not a
                           # spelling of this one.
    \s+                    # TOLERANCE, one-or-more. A person types a second
                           # space and cannot see it. Withdraw this only if a
                           # single space becomes enforceable at every
                           # producer, and producer 3 is a human, so it cannot.
    \d{4}-\d{2}-\d{2}      # The date. NO TOLERANCE on the widths or the
                           # separator: a fixed-width date is what makes this
                           # predicate decidable, and every producer that
                           # emits a date emits this shape.
    (?:\s+\d{2}:\d{2})?    # TOLERANCE, the whole time group is OPTIONAL, and
                           # this is the load-bearing one. Producers 1 and 2
                           # always emit a time, so this branch exists for
                           # producer 3 alone. REMOVE IT and a hand-written
                           # date-only entry counts as a PIN, the count rises,
                           # and a faithful edit is DENIED. That is an
                           # over-block and it is the cardinal direction.
                           # KEEP IT and a pin titled a bare date with no
                           # marker drops out of the count, which is an
                           # under-block over a population a user ruling
                           # declares empty. Withdraw this only when that
                           # ruling is withdrawn.
    \s*$                   # TOLERANCE, zero-or-more, AND THE ANCHOR IS NOT
                           # part of it. Trailing space is invisible to a
                           # person and must not change a verdict. THE `$`
                           # BESIDE IT IS NOT A TOLERANCE AND MUST NOT BE
                           # WIDENED: let text follow the date and
                           # `### 2026-08-05 Draft notes` stops counting as a
                           # pin, so a user who RENAMES that pin to drop the
                           # date loses a title from the old count and the
                           # gate FIRES on a faithful rename. The user ruling
                           # covers a BARE date only, so it does not cover
                           # that class.
    """,
    re.VERBOSE,
)


def _is_memory_entry(pin) -> bool:
    """Report whether a parsed entry is a memory entry rather than a pin.

    THE PREDICATE IS A CONJUNCTION AND EACH HALF IS LOAD-BEARING. An entry is a
    memory entry when its heading is DATE-LED and it carries NO
    `<!-- pinned: -->` marker. The date alone does not decide: a curator can
    title a pin with a date, and that pin carries a marker.

    WHY THE DATE ALONE CANNOT DECIDE, WHICH IS A PROOF RATHER THAN A PREFERENCE.
    A hand-written date-only memory entry and a pin titled a bare date are THE
    SAME STRING, and the two want opposite verdicts. So no function of the
    heading alone returns two answers, whatever it is spelled as. The marker is
    the second signal that makes the two separable.

    THE RESIDUAL THIS CARRIES, RECORDED RATHER THAN HIDDEN.
      R1, an add of a date-titled pin with NO marker, is not counted, so the
      gate stays quiet. That direction is an under-block.
      R2, an edit that ADDS a missing marker to a date-titled pin, moves no
      pin, and this predicate counts 0 then 1, so the gate FIRES. That
      direction is a cardinal OVER-BLOCK.
    THE TRIGGER FOR THE TWO IS ONE POPULATION: a date-titled pin with no
    marker. A USER RULING DECLARES THAT POPULATION EMPTY, because a pin is not
    written that way in good faith. THE RULING IS WHAT MAKES R2 ACCEPTABLE, and
    R2 is cardinal, so the ruling carries more weight than the under-block it
    was first priced against.

    WHAT MAKES THE POPULATION NON-EMPTY AGAIN, WHICH IS THE THING TO WATCH: a
    writer that emits a pin with a bare-date title and no marker. If one
    appears, R1 and R2 stop being hypothetical and this predicate wants a
    re-price rather than a patch.

    A GUARD ON THE MARKER-ADDING EDIT WAS CONSIDERED AND REFUSED, AND THE
    REASON IS THE TRADE RATHER THAN AN IMPOSSIBILITY. An earlier note here said
    such a guard cannot separate the marker-adding edit from a true add without
    reading a file the edit has not landed in. THAT REASON IS RETIRED: the
    separation was driven, and the fragment IS resolvable against the file on
    disk. `_fragment_reaches_pinned_region` below does that read today.
    THE TRADE IS WHAT REFUSES THE GUARD, and it is a set difference:
      THE CANDIDATE, the strongest of the two that were driven: if the MULTISET
      of `### ` heading lines is unchanged across the edit, no heading
      appeared, so no pin appeared. Decline.
      IT CLOSES R2. IT OPENS B3, A PROMOTION: a date-titled entry moves from
      Working Memory INTO the pinned region and gains a marker. The heading
      multiset is unchanged, so the guard declines a GENUINE pin add.
      B3 IS REACHABLE IN GOOD FAITH. Promotion of an entry to a pin is the
      purpose of the pin command, and a user who does it by hand writes that
      edit with no knowledge of this gate. It is not the deliberate class this
      project treats as tolerable.
    AND THE TRIGGER IS EMPTY, WHICH IS THE SECOND AND INDEPENDENT REASON. R2
    needs a date-titled pin with NO marker, and a user ruling declares that
    population empty. So the guard is INSURANCE, its premium is a reachable
    missed add, and the insured event is one the ruling says does not happen.
    IF A WRITER EVER EMITS A BARE-DATE PIN WITH NO MARKER, this ruling is the
    one to re-open first, and the project rule then decides it the other way,
    because a live cardinal over-block outranks a missed staleness reminder.

    🔴 THE RECIPROCAL HALF OF A COUPLING, PLACED AT THE SITE OF THE EDIT THAT
    WOULD REMOVE IT. This exclusion and the whole-text fallback in
    `_counts_show_an_add` ARE A PAIR. The fallback keeps the memory entries in
    the slice, and THIS function is what drops them. Delete this predicate and
    the fallback alone re-introduces the over-count that the pair exists to
    remove. Do not remove one without the other, and read the matching sentence
    at the fallback arm before you change either. Each one alone is worse than
    the pair.
    """
    if not _DATE_LED_HEADING_RE.match(pin.heading.strip()):
        return False
    return pin.date_comment is None


def _count_pin_comments(text: str) -> int:
    """Count pins using `parse_pins` as the canonical oracle.

    Symmetric-oracle invariant (closes 2 HIGH bypasses): the gate MUST
    count pins using the same parser that enforces the count cap at
    add-time (`pin_caps.parse_pins`). A regex substring count of
    `<!-- pinned:` is asymmetric with `parse_pins`, which:
      (a) recognizes a bare `### Heading` (no date comment) as a Pin,
      (b) tolerates arbitrary whitespace between `<!--` and `pinned:`
          via its `\\s*` patterns (e.g. `<!--  pinned:` double-space),
      (c) matches case-insensitively.
    Substring counts undercount (a) and (b), letting an adversarial ADD
    slip past the ADD-shape gate while still landing in CLAUDE.md as a
    parse_pins-visible pin.

    THIS FUNCTION DOES NOT CHOOSE A SLICE, AND IT USED TO. It counted the
    managed region when the markers were present and the whole text when they
    were not, so the branch was decided PER STRING. The two sides of one
    decision could then reach different branches, and a difference taken across
    two different slices is not a comparison. That is the STRADDLE, and it bit
    in the two directions: a straddle over-blocked when no pin moved, and a
    straddle MISSED a true add of four pins to five.

    THE SLICE NOW BELONGS TO THE DECISION, in `_counts_show_an_add`, which is
    the only place that can see the two sides at one time. This function counts
    across the body its caller supplies and nothing else. (`_is_add_shaped_edit`
    chooses WHICH comparison runs, the whole-document one or the fragment one.
    It does not choose the slice, and an earlier revision of this paragraph
    named it as if it did.)

    THE COUNT PREDICATE, WHICH IS THE OTHER HALF OF THE PAIR. `parse_pins`
    stays the oracle, so the symmetric-oracle invariant above holds. One class
    is then dropped from the result: a heading that is date-led AND carries no
    `<!-- pinned: -->` marker is a memory entry rather than a pin. See
    `_is_memory_entry` for the residual this predicate carries and for the
    population a user ruling declares empty.

    Fail-open: non-str input returns 0. Any parse_pins failure (should
    not raise by its own contract, but defense-in-depth) returns 0.
    """
    if not isinstance(text, str):
        return 0
    try:
        return sum(1 for pin in parse_pins(text) if not _is_memory_entry(pin))
    except Exception:  # noqa: BLE001 — fail-open
        return 0


def _counts_show_an_add(old_text: str, new_text: str) -> bool:
    """Compare the two sides of ONE decision across ONE slice.

    RULE 1, AND IT IS THE WHOLE REASON THIS FUNCTION EXISTS. A difference taken
    across two DIFFERENT slices is not a comparison. The counter used to pick
    its own slice per string, so the two sides of one decision could reach
    different branches. That is the STRADDLE and it bit in the two directions:
    one straddle over-blocked when no pin moved, and one MISSED a true add of
    four pins to five.

    THE SELECTION, and it is a TOTAL function with no decline arm:
      0. LOCUS FIRST. Ask each side for its `## Pinned Context` span. If BOTH
         sides resolve one, that section is the slice for the two.
      1. Otherwise, ask each side whether it carries the managed markers.
      2. If the two agree, use that branch for the two.
      3. If the two disagree, use the WHOLE TEXT for the two.
    The whole text is a slice each side can always carry, so there is no
    failure direction to choose here and no exception arm to add.

    STEP 0 IS THE LOCUS BOUND, AND ITS SAFETY IS A SUBSET RELATION RATHER THAN
    A CASE LIST. It narrows the slice ONLY where both sides resolve a pinned
    section, and it falls back to the shipped selection everywhere else, so the
    documents it treats differently are a STRICT SUBSET of the ones the shipped
    selection got wrong. It cannot be worse on the cardinal axis, for any
    document, including shapes nobody has enumerated.
    WHY BOTH SIDES AND NOT ONE. A bound taken from ONE side counts 0 against 0
    on any payload that carries no heading, and every Edit fragment is such a
    payload, so the gate would stop firing on the whole Edit branch. That is a
    MISSED ADD, and it is the direction this counter exists to close. Measured:
    the one-sided form fixes five over-blocks and opens two missed adds. The
    two-sided form fixes two and opens none.

    WHAT STEP 0 DOES NOT CLOSE, RECORDED SO A LATER READER DOES NOT READ THE
    LOCUS AS COMPLETE. A document with NO `## Pinned Context` heading has NO
    span, so the position is UNDEFINED rather than unavailable, and no file
    read and no instrument change supplies one. A prose-titled entry added to
    such a document continues to over-block. THE POPULATION IS NOT HAND EDITS
    ALONE: a memory-record field value can carry a prose title into the managed
    region, so a machine writer reaches this shape with no human in the route,
    and a fresh project file with no pins is exactly this shape.
    WHAT WOULD MAKE IT REDUCIBLE: a SECOND ANCHOR. These documents carry a
    `## Working Memory` heading, and a predicate that treats a heading below
    that anchor as a memory entry has a defined position. That is a new
    predicate with its own failure direction, so it is recorded as a route and
    not taken here.

    🔴 THE WHOLE-TEXT FALLBACK KEEPS THE MEMORY ENTRIES. `_is_memory_entry` IS
    WHAT DROPS THEM. DO NOT REMOVE THE DATE-LED EXCLUSION AND KEEP THIS
    FALLBACK: the pair is correct and each one alone is worse than the pair.
    Measured, the wider slice alone re-introduces the over-count this repair
    exists to remove.

    THE EXCEPTION BEHAVIOUR IS UNCHANGED. This selects a slice. The fail-open
    arms that the caller declares SACROSANCT stay where they are.
    """
    # THESE IMPORTS ARE FUNCTION-LOCAL AND THAT IS THE EXCEPTION POSTURE, NOT A
    # STYLE CHOICE. A raise from either one lands inside the caller's
    # SACROSANCT fail-open catch, so an unresolvable import ALLOWS the edit.
    # That is the correct direction for this gate and it is the direction the
    # module-load block at the top deliberately does NOT take. Moving either
    # import to module scope would put it under the fail-CLOSED load wrapper
    # and turn a missing dependency into a DENY of the user's own edit.
    from shared.claude_md_manager import extract_managed_region
    from staleness import _parse_pinned_section

    # STEP 0, THE LOCUS BOUND. `allow_empty_section=True` is what makes an
    # EMPTY pinned section resolve. Without it an empty section is
    # indistinguishable from an absent one, this step declines, and the empty
    # side falls back to a wider slice while the other side does not. That is
    # the straddle again, in a new place.
    old_pinned = _parse_pinned_section(old_text, allow_empty_section=True)
    new_pinned = _parse_pinned_section(new_text, allow_empty_section=True)
    if old_pinned is not None and new_pinned is not None:
        return (
            _count_pin_comments(new_pinned[2])
            > _count_pin_comments(old_pinned[2])
        )

    old_is_managed = extract_managed_region(old_text) is not None
    new_is_managed = extract_managed_region(new_text) is not None

    if old_is_managed and new_is_managed:
        old_slice = extract_managed_region(old_text)[0]
        new_slice = extract_managed_region(new_text)[0]
    else:
        # Either the two sides agree that no managed region is present, or they
        # DISAGREE and the whole text is the slice the two can always carry.
        old_slice = old_text
        new_slice = new_text

    return _count_pin_comments(new_slice) > _count_pin_comments(old_slice)


def _changed_span_offsets(old_string: str, new_string: str) -> tuple[int, int]:
    """Return the common prefix length and the common suffix length.

    AN EDIT REPLACES A FRAGMENT, AND MOST OF THAT FRAGMENT USUALLY SURVIVES.
    The common prefix and the common suffix are the parts that do not move.
    What lies between them is the text the edit CHANGED, and that is the part
    whose position decides whether the edit reaches the pinned region.

    The two lengths never overlap: the suffix scan stops at the prefix, so a
    payload where one side contains the other reports the shorter side fully
    as prefix and reports no suffix.
    """
    limit = min(len(old_string), len(new_string))
    prefix_len = 0
    while prefix_len < limit and old_string[prefix_len] == new_string[prefix_len]:
        prefix_len += 1
    suffix_len = 0
    while (
        suffix_len < limit - prefix_len
        and old_string[len(old_string) - 1 - suffix_len]
        == new_string[len(new_string) - 1 - suffix_len]
    ):
        suffix_len += 1
    return prefix_len, suffix_len


def _fragment_reaches_pinned_region(
    old_string: str, new_string: str, claude_md_path: Path
) -> bool | None:
    """Report whether an Edit fragment touches the Pinned Context section.

    AN EDIT PAYLOAD CARRIES NO SECTION HEADING, so the two fragments alone
    cannot say WHERE the edit lands, and the gate used to fire on a memory
    entry added far outside the pinned region. The position is not missing: the
    caller holds the path, the tool contract makes `old_string` UNIQUE in the
    file, and the file on disk is the pre-edit state. So the offset is a read
    away.

    THREE OUTCOMES, AND THE THIRD IS NOT A FAILURE:
      True  - the fragment overlaps the pinned span. Compare the counts.
      False - the fragment is wholly OUTSIDE the span, or the position could
              not be established. Do not fire.
      None  - NO PINNED SPAN EXISTS, so the locus test cannot run at all.
              The caller proceeds with the comparison it would have made
              before this function existed.

    🔴 THE FALSE ARM AND THE None ARM LOOK ALIKE AND MUST NOT BE MERGED. Both
    mean "no span to test against", and they take OPPOSITE directions on
    purpose. A failed READ is an instrument failure: nothing is known, so the
    safe direction is quiet. A document with NO `## Pinned Context` heading is
    a KNOWN state whose span is UNDEFINED, and answering False there would
    silence the gate on every unmarked document. That is not a repair, it is
    suppression, and it would read as a repair because the suite would go
    green. Merge these two arms and the gate stops working.

    FAIL OPEN, AND THE TWO CASES ARE NAMED. A read that raises, and a fragment
    that is NOT UNIQUE, both answer False. Non-uniqueness is what a
    `replace_all` payload produces: it removes the uniqueness the tool contract
    otherwise supplies, so no single offset exists and there is nothing to test.
    Quiet is an under-block on a staleness reminder, which this project ranks
    below a cardinal over-block on the user's own file.

    AN EMPTY `old_string` IS THE None ARM AND NOT THE False ARM. There is no
    fragment to locate, and answering False would drop a real add-detection:
    the shipped comparison counts 0 against N for that payload and FIRES.
    """
    if not old_string:
        return None

    from staleness import _parse_pinned_section

    try:
        content = claude_md_path.read_text(encoding="utf-8")
    except (IOError, OSError, UnicodeDecodeError):
        return False

    parsed = _parse_pinned_section(content, allow_empty_section=True)
    if parsed is None:
        return None

    pinned_start, pinned_end, _ = parsed

    if content.count(old_string) != 1:
        return False

    offset = content.find(old_string)

    # TEST THE TEXT THE EDIT CHANGED, NOT THE FRAGMENT IT ANCHORED ON. THE
    # COUNT MEASURES WHAT THE EDIT ADDED, SO THE LOCUS MUST MEASURE THE SAME
    # THING. An anchor offset and an added-text position agree everywhere
    # except at a boundary, and the boundary is where the anchor measures the
    # incorrect object.
    #
    # WHY THE ANCHOR FAILS THERE, AND IT IS NOT A TUNING QUESTION. An Edit
    # REPLACES its fragment, so an insertion anchors on the text that FOLLOWS
    # the insertion point. Two edits then share one anchor offset:
    #   a pin added IN FRONT of the terminator, which lands INSIDE the section,
    #   an entry added AFTER the terminator, which lands OUTSIDE it.
    # NO PREDICATE OVER THE ANCHOR OFFSET SEPARATES THOSE TWO. An earlier form
    # here tested the anchor with inclusive bounds. It answered the first row
    # correctly and OVER-BLOCKED the second, which moves the harm to the
    # cardinal axis. A strict form answered the second correctly and MISSED
    # the first, which is the direction this counter exists to close. The
    # trade was a false choice, and the changed span removes it.
    #
    # THE COMMON PREFIX IS WHAT LOCATES THE ADDED TEXT. It is the run the two
    # sides share, so the first character the edit changes sits at the anchor
    # offset plus its length. In the two rows above the prefix differs, which
    # is the property the anchor offset cannot see.
    prefix_len, suffix_len = _changed_span_offsets(old_string, new_string)
    changed_start = offset + prefix_len
    changed_end = offset + len(old_string) - suffix_len

    # A PURE INSERTION HAS AN EMPTY CHANGED SPAN, AND AN EMPTY SPAN STILL HAS A
    # POSITION. The inclusive comparison is what makes an insertion AT a
    # boundary count as reaching the region, which a width-based test would
    # drop.
    #
    # FAILURE DIRECTION. Over-reach: none measured across the three rows.
    # Under-reach: a payload with NO common prefix puts `changed_start` at the
    # anchor offset, so this degrades to the anchor test rather than to
    # silence. NULL OUTCOME: a document with no pinned span cannot run this
    # test at all, which is N1 and is handled above.
    return changed_start <= pinned_end and changed_end >= pinned_start


def _is_add_shaped_edit(
    tool_input: dict, claude_md_path: Path, tool_name: str = ""
) -> bool:
    """Return True if the Edit/Write adds a net-new pin comment.

    The marker-gate fires only on ADD-shaped edits so the user can still
    ARCHIVE stale pins (reducing pin count) to resolve the condition.
    Archival edits (old_string contains `<!-- pinned:`, new_string does
    not, or count strictly decreases) and refactor edits (pin count
    unchanged) are allowed.

    For Edit tool:
      - ADD: new_count > old_count in the replacement strings
      - ARCHIVE: new_count < old_count  → allow
      - REFACTOR: new_count == old_count → allow (pin body rewrite,
        STALE marker injection, etc.)

    For Write tool (full-file replacement):
      - Compare pin count in new content vs. current on-disk content.
      - ADD: new file has MORE pin comments than current → block
      - Otherwise → allow

    Fail-open: any shape-detection error returns False (allow). This
    preserves the SACROSANCT gate invariant.
    """
    # WHY net-new detection: the gate exists to stop the user adding a 13th
    # pin while stale pins remain. Archival is the REMEDIATION the user is
    # directed to perform — denying it causes a same-session livelock
    # (reviewer-security F1). A substring match on `<!-- pinned:` is
    # symmetric across add and archive shapes, so it cannot distinguish
    # them. A strict count increase is asymmetric by construction: ADD
    # raises the count, ARCHIVE lowers it, REFACTOR leaves it unchanged.
    try:
        # RULE 4, THE TOOL NAME. The caller knows the tool, because it checked
        # it against `_GATED_TOOLS`, so this branch asks the tool rather than
        # guessing from a payload key. A non-Write tool carrying a `content`
        # key took the whole-document branch before this.
        #
        # 🔴 THIS DOES NOT REACH THE STRADDLE, and a reader must not take it
        # for a straddle repair. It selects WHICH COMPARISON runs. The straddle
        # lives inside the comparison, in the slice each side reached, and
        # `_counts_show_an_add` is what closes that.
        if tool_name:
            is_write = tool_name == "Write"
        else:
            is_write = "content" in tool_input
        if is_write:
            # Write tool — diff against current file content.
            new_content = tool_input.get("content", "")
            if not isinstance(new_content, str):
                return False
            try:
                current = claude_md_path.read_text(encoding="utf-8")
            except (IOError, OSError, UnicodeDecodeError):
                # Cannot compare → fail-open.
                return False
            return _counts_show_an_add(current, new_content)

        # Edit tool — compare old_string vs new_string pin counts.
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        if not isinstance(old_string, str) or not isinstance(new_string, str):
            return False
        # THE LOCUS TEST RUNS BEFORE THE COUNT, because a fragment outside the
        # pinned region cannot add a pin to it whatever its counts say. A None
        # answer means no span exists, so the comparison below runs unchanged.
        reaches = _fragment_reaches_pinned_region(
            old_string, new_string, claude_md_path
        )
        if reaches is False:
            return False
        return _counts_show_an_add(old_string, new_string)
    except Exception:  # noqa: BLE001 — SACROSANCT fail-open
        return False


def _check_tool_allowed(input_data: dict) -> str | None:
    """Determine whether the tool call should be denied.

    Returns the deny reason string if blocked, or None to allow.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in _GATED_TOOLS:
        return None

    pact_context.init(input_data)

    # Lead-role gate (#878, DENY-gate enforcement RESTORATION) — teammates
    # don't edit project CLAUDE.md (worktree scope rule), so this gate is
    # team-lead-only. Migrated from the negative `resolve_agent_name(...) != ""`
    # heuristic — which returned non-empty for BOTH lead spellings, so the lead
    # itself took this bypass branch and the DENY gate was silently DEAD for
    # the lead. is_lead keys on the harness-set agent_type directly; it is total
    # (never raises), preserving the caller's existing exception posture — which
    # for this gate is fail-OPEN (the SACROSANCT default: any exception in gate
    # logic allows the edit). A raising predicate would have perturbed that.
    if not pact_context.is_lead(input_data):
        return None

    session_dir = pact_context.get_session_dir()
    if not session_dir:
        return None

    marker_path = Path(session_dir) / PIN_STALENESS_MARKER_NAME
    if not marker_path.exists():
        return None

    tool_input = input_data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return None

    file_path_str = tool_input.get("file_path", "")
    claude_md_path = match_project_claude_md(file_path_str)
    if claude_md_path is None:
        return None

    # Narrow matcher: block only ADD-shaped edits (net-new pin comment).
    # Archival edits (pin removal) and refactor edits (pin body rewrite)
    # are allowed so the user can resolve the stale-pins condition by
    # running /PACT:pin-memory within the same session. Fix for #492
    # F1 marker livelock.
    if not _is_add_shaped_edit(tool_input, claude_md_path, tool_name):
        return None

    return _DENY_REASON


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(_SUPPRESS_OUTPUT)
        sys.exit(0)

    try:
        deny_reason = _check_tool_allowed(input_data)
    except Exception:
        # SACROSANCT: any exception in gate logic → fail-open.
        print(_SUPPRESS_OUTPUT)
        sys.exit(0)

    if deny_reason:
        # hookEventName is required by the harness; missing it silently fails open
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_reason,
            }
        }
        print(json.dumps(output))
        sys.exit(2)

    print(_SUPPRESS_OUTPUT)
    sys.exit(0)


if __name__ == "__main__":
    main()
