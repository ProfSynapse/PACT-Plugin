"""
Staleness Detection Module

Location: pact-plugin/hooks/staleness.py

Summary: Detects stale pinned context entries in the project CLAUDE.md and
checks whether pinned content exceeds its token budget. Stale entries are
marked with HTML comments so they can be identified for cleanup.

Used by:
- session_init.py: Calls check_pinned_staleness() during SessionStart hook
- Test files: test_staleness.py tests all functions in this module

Extracted from session_init.py to keep that file focused on hook orchestration
and under the 500-line maintainability limit.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from shared.claude_md_manager import (
    PACT_BOUNDARY_PREFIXES,
    PINNED_END_MARKER,
    extract_managed_region,
)
from pin_caps import (
    PIN_STALE_BLOCK_THRESHOLD,
    CapViolation,
    check_stale_block,
    parse_pins,
)

# Boundary prefix alternation used by _parse_pinned_section. Built from
# PACT_BOUNDARY_PREFIXES (round 5, item 1) so the three-prefix union is
# defined in one place.
_BOUNDARY_ALT = "|".join(PACT_BOUNDARY_PREFIXES)

# NOTE FOR ANYONE RE-ADDING A PROBE PATTERN HERE. A second alphabet used to live
# at this spot, for a well-formedness gate that tried to DETECT the cases where a
# declared end over-reaches. It was narrower than the terminator alternation it
# guarded, so it caught the heading cases and missed the boundary-comment ones,
# and that shipped a cardinal over-block. The gate is gone: `_parse_pinned_section`
# now BOUNDS the declared end instead of policing it, so there is no second
# alphabet to keep in sync and nothing here to widen.


# Staleness detection constants

# Number of days after which a pinned entry referencing a merged PR is
# considered stale and gets an HTML comment marker.
PINNED_STALENESS_DAYS = 30

# Approximate token budget for the entire Pinned Context section. When
# exceeded, a warning comment is added. No pin is ever deleted.
# This is the sole definition of this constant; session_init.py imports it.
#
# SIZED FROM CAPACITY, NOT FROM A MEASUREMENT OF THE CURRENT DOCUMENT. A bound
# derived from the region it bounds cannot see that region's next edit, and it
# lands so close to the present size that an ordinary pin edit re-trips the
# warning -- which reports "you touched a pin", not "your pins have bloated".
# This value leaves headroom above a full set of well-written pins.
#
# WHY THIS IS A FREE NUMBER RATHER THAN A VALUE DERIVED FROM THE CAPS IN
# pin_caps.py. A derived advisory cannot fire before enforcement binds. If the
# budget were f(caps) with f >= 1, then reaching it would require roughly full
# legal capacity -- and at that point PIN_SIZE_CAP and PIN_COUNT_CAP are
# already refusing edits, so the advice arrives at the wall, too late to act
# on. Advising EARLIER requires a coefficient below 1. Derivation therefore
# does not eliminate the free number; it relocates it into a coefficient. This
# constant IS that coefficient, stated directly instead of hidden in a formula.
#
# The two also bound DIFFERENT things, which is why one cannot be read off the
# other: PIN_SIZE_CAP counts body characters of a single pin, while this counts
# estimated tokens of the whole section, headings and markers included.
PINNED_CONTEXT_TOKEN_BUDGET = 3200

# The exact text this module writes at the head of an over-budget pinned
# section. It is BOTH the text of the warning and the probe that finds an
# earlier one, so the writer and the reader cannot describe different things.
_BUDGET_WARNING_PREFIX = "<!-- WARNING: Pinned context"

# THE SHAPE OF A WARNING LINE, WITHOUT AN ANCHOR. This is a regex SOURCE
# STRING and not a compiled pattern, on purpose: an un-anchored shape is not
# callable, so no call site can obtain a position-blind predicate by accident.
# The two compositions below are the only predicates that exist.
#
# THE SHAPE CARRIES ITS OWN BOUNDS. `[^\n]*?` cannot cross a newline, so the
# match always ends inside the line it starts on, and it is LAZY so it stops at
# the FIRST `-->`. An HTML comment ends at its first `-->`; a greedy run to the
# LAST one on the line would swallow whatever a user appended after the comment
# had already closed.
#
# THE `~N tokens (budget: M)` SHAPE IS LOAD-BEARING, NOT DECORATION. It is what
# separates a line this module emitted from a line that merely opens with the
# same words, and requiring it is what keeps the strip off a user's own prose.
#
# THIS SHAPE AND THE EMITTED FORMAT IN `apply_staleness_markings` ARE A MATCHED
# PAIR. Change one and change the other in the SAME commit: a format this shape
# cannot match is a warning that can never be refreshed or removed, and every
# later pass stacks another warning above it.
_BUDGET_WARNING_SHAPE = (
    rf"{re.escape(_BUDGET_WARNING_PREFIX)} ~\d+ tokens \(budget: \d+\)[^\n]*?-->\n?"
)

# Matches ONE complete warning comment line at the very head of a pinned body.
#
# EACH PATTERN CARRIES ITS OWN ANCHOR, so no call site can widen it. `\A` pins
# the match to offset 0, the only offset this module ever writes such a line to.
# The shape above is deliberately left uncompiled, so it is not callable as a
# predicate and the anchor cannot be chosen by a caller.
#
# STRICT ON PURPOSE. This predicate DELETES bytes from a user's CLAUDE.md, a
# file that is frequently gitignored, so an over-match has no commit to recover
# from. A loose variant that matched anywhere in the region would also reach
# text a user wrote inside a pin body. Compare `_find_declared_end_offset`:
# a predicate's tolerance follows its failure direction, never its resemblance
# to a predicate that looks like it.
#
# THE SYMPTOM THAT WILL MAKE SOMEBODY WANT TO LOOSEN THIS, AND WHY TO REFUSE.
# A user who moves a warning line below the head keeps it, because this
# predicate is anchored and cannot reach it. The report arrives as "the hook
# shows two warnings", or as "the hook reports a breach my own pins did not
# cause", because that line is measured with the rest of the body. Both are
# real, and both are accepted. The law is CONDITIONAL, not a constant:
#     count = N + (1 if estimate_tokens(user_text + stranded) > BUDGET else 0)
# where N is the number of lines the user moved below the head. No pass raises
# the count.
#
# DO NOT WIDEN THIS PATTERN TO REACH THEM. It DELETES, so a wider anchor reaches
# text a user wrote inside a pin body, and this file is frequently gitignored.
# The correct repair separates the two questions: EXCLUDE lines of this shape
# from the COUNT wherever they sit, and keep the DELETE on the contiguous head
# run. Apply that exclusion to a THROWAWAY COPY at the measurement site. Never
# modify `pinned_content` itself -- `entry_starts` holds offsets into that
# string and the stale-marker loop writes at those offsets, so an in-place
# exclusion puts markers in wrong positions. The exclusion looks like a pure
# read, which is what makes that easy to miss.
_LEADING_BUDGET_WARNING_RE = re.compile(rf"\A{_BUDGET_WARNING_SHAPE}")

# RECOGNITION ONLY. NEVER GIVE THIS PATTERN TO CODE THAT DELETES. `(?m)^`
# reports a match at ANY line start, which is what lets `_has_budget_warning`
# see a warning a user has moved below the head. The deleting anchor stays
# inside the compiled object above, so this wider reach cannot travel to it.
_ANY_BUDGET_WARNING_RE = re.compile(rf"(?m)^{_BUDGET_WARNING_SHAPE}")


def _find_existing_claude_md(base: Path) -> Optional[Path]:
    """
    Look for an existing project CLAUDE.md under `base`, honoring both
    supported locations: `.claude/CLAUDE.md` (preferred) then `CLAUDE.md`
    (legacy). Returns the first match or None.
    """
    dot_claude = base / ".claude" / "CLAUDE.md"
    if dot_claude.exists():
        return dot_claude
    legacy = base / "CLAUDE.md"
    if legacy.exists():
        return legacy
    return None


def _resolve_project_claude_md_with_base() -> Tuple[Optional[Path], Optional[Path]]:
    """
    Resolve the project-level CLAUDE.md AND the trusted base directory it was
    found under, so a write caller can containment-check the target against the
    base the resolver actually used (#1247).

    Honors both supported locations:
      - $base/.claude/CLAUDE.md  (preferred / new default)
      - $base/CLAUDE.md          (legacy)

    Resolution order for $base:
      1. CLAUDE_PROJECT_DIR env var
      2. Git common-dir parent (worktree-safe; --show-toplevel would return
         the worktree path, which often does not contain CLAUDE.md)
      3. Current working directory

    The returned `base` is the branch's directory captured BEFORE descending
    into `.claude` (the arg to `_find_existing_claude_md`), NOT the returned
    path and NOT a re-derivation -- the trusted pre-resolve anchor that makes
    the #1247 containment check non-vacuous. `get_project_claude_md_path` is
    now a thin wrapper returning `[0]`, so read-only callers and the
    resolver-parity lint are unaffected.

    Returns:
        (path, base) where path is an existing project CLAUDE.md and base is
        the directory it was found under; (None, None) if none exists.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        base = Path(project_dir)
        found = _find_existing_claude_md(base)
        if found is not None:
            return found, base

    # Fallback: detect git root (worktree-safe)
    # Uses --git-common-dir instead of --show-toplevel because the latter
    # returns the worktree path when run inside a worktree, which may not
    # contain CLAUDE.md. --git-common-dir always points to the shared .git
    # directory; its parent is the main repo root where CLAUDE.md lives.
    # git returns this path relative to the invoking directory when run at a
    # repo root (the bare ".git") and absolute elsewhere, so resolve a relative
    # result against the cwd before taking its parent.
    # NOTE: Twin pattern in skills/pact-memory/scripts/memory_api.py
    #       (_detect_project_id) and working_memory.py (_get_claude_md_path)
    #       -- keep in sync.
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            common_dir = Path(result.stdout.strip())
            if not common_dir.is_absolute():
                common_dir = Path.cwd() / common_dir
            repo_root = common_dir.resolve().parent
            found = _find_existing_claude_md(repo_root)
            if found is not None:
                return found, repo_root
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Last resort: current working directory
    cwd = Path.cwd()
    found = _find_existing_claude_md(cwd)
    return (found, cwd) if found is not None else (None, None)


def _lexical_base_of(claude_md_path: Path) -> Path:
    """Recover the pre-`.claude` base of a resolver-produced CLAUDE.md path by
    INVERTING the resolver's construction (base/.claude/CLAUDE.md | base/
    CLAUDE.md) -- #1247 option D, for a caller-SUPPLIED path with no separate
    base (session_init's production flow passes the path, not the base).

    Purely lexical (pathlib `.parent` never follows symlinks), so an F1
    symlinked-parent `.claude` still escapes on the target's resolve() and is
    refused. Locked to the resolver's own base by TestStalenessLexicalBaseParity
    -- if _resolve_project_claude_md_with_base ever grows a third path shape,
    that test turns this formula's divergence into a RED.

    Edge (adversarial-only UNDER-block, tolerated per the good-faith model): a
    project dir literally named ".claude" using the LEGACY layout lands one
    level too high. Requires deliberate construction; not a bug.
    """
    if claude_md_path.parent.name == ".claude":
        return claude_md_path.parent.parent
    return claude_md_path.parent


def get_project_claude_md_path() -> Optional[Path]:
    """
    Get the path to the project-level CLAUDE.md (path only).

    Thin wrapper over `_resolve_project_claude_md_with_base` (added for #1247);
    read-only callers, session_init, and the resolver-parity lint use this
    Path-only name, while the write caller (check_pinned_staleness) uses the
    with-base variant to get the containment anchor.

    Returns:
        Path to an existing project CLAUDE.md if found, None otherwise.
    """
    return _resolve_project_claude_md_with_base()[0]


# Backward-compatible alias (tests and session_init patch the underscore name)
_get_project_claude_md_path = get_project_claude_md_path


def estimate_tokens(text: str) -> int:
    """
    Estimate token count using word count * 1.3 approximation.

    NOTE: Twin copy exists in working_memory.py (_estimate_tokens) -- keep in sync.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


# Backward-compatible alias (tests and session_init import the underscore name)
_estimate_tokens = estimate_tokens


def _strip_budget_warnings(pinned_content: str) -> str:
    """
    Remove the run of budget-warning comment lines at the head of a pinned body.

    Returns the body a user would have written, with this module's own earlier
    reports taken back out. Callers measure the RESULT, never the input, so the
    reported count never includes the warning this module wrote at the HEAD. It
    is NOT a pure function of the user's own text: a warning a user has moved
    below the head survives this strip and is measured with the body. The note
    at `_LEADING_BUDGET_WARNING_RE` says why the repair for that is not a wider
    strip.

    A run, not a single line, because taking back N lines is the exact inverse
    of writing one -- so the function stays correct if a document somehow
    carries more than one, and it can never leave a partial residue behind.

    Args:
        pinned_content: The pinned section body.

    Returns:
        The body with any leading budget-warning lines removed.
    """
    while True:
        match = _LEADING_BUDGET_WARNING_RE.match(pinned_content)
        if match is None:
            return pinned_content
        pinned_content = pinned_content[match.end():]


def _has_budget_warning(pinned_content: str) -> bool:
    r"""
    Report whether this module has already written a warning anywhere in
    `pinned_content`.

    RECOGNITION, NOT DELETION, AND THAT IS WHY THE ANCHOR DIFFERS. This
    predicate and `_strip_budget_warnings` share ONE shape,
    `_BUDGET_WARNING_SHAPE`, and differ only in position: the strip takes back
    the run at offset 0, this reports a match at ANY line start. The shape is
    what identifies a line as this module's own, so the wider anchor does not
    widen what counts as a warning. The narrower anchor stays INSIDE the
    pattern the strip uses, so no call site can widen what gets deleted.

    DO NOT MERGE THE TWO INTO ONE PATTERN CHOSEN BY THE CALL SITE. That works
    -- `.match` on a line-anchored pattern is identical to `\A` -- and it puts
    the deleting anchor where a later edit can move it. The cardinal failure
    here is deletion of a user's own text from a file that is frequently
    gitignored.

    THE ACCEPTED CONSEQUENCE, RULED ON AND NOT OVERLOOKED. A user can write a
    complete warning line into their own pinned prose: a maintainer who pastes
    the emitted format into a note is the realistic case. In a section with NO
    entries, that body now enters the pass. If it ALSO exceeds the budget, this
    module adds ONE current warning above it. BOTH conditions are required. A
    quoted line in a body below the budget changes nothing at all.

    THIS COST IS NOT NEW, AND THAT IS THE REASON TO ACCEPT IT. A section WITH
    entries has always behaved this way, and the suite pins it: see
    `test_user_line_quoting_the_warning_is_preserved`, which asserts a count of
    two for a pin body that quotes the warning. The two documents differ only
    in whether they hold an entry, so they must not differ here. The corner was
    the inconsistency, and this is the repair.

    The cost is also the smaller of the two failures, which is a second and
    subordinate reason. One extra advisory line is visible, it stays at one on
    every later pass, and the user can delete it. The alternative was to leave
    the corner alone, which keeps a stale number in the document without limit
    and announces nothing.

    Args:
        pinned_content: The pinned section body.

    Returns:
        True when a budget warning this module wrote sits at any line start.
    """
    return _ANY_BUDGET_WARNING_RE.search(pinned_content) is not None


def _find_terminator_offset(
    content: str,
    start: int,
    terminator_pattern: "re.Pattern[str]",
) -> int:
    """
    Find the absolute offset of the first line matching `terminator_pattern`.

    Simple line-by-line search — no fence tracking needed because callers
    operate within the PACT-managed region (round 10 structural guarantee).
    The managed region contains only plugin-generated content; user-authored
    fenced code blocks live outside PACT_MANAGED_START/END.

    Args:
        content: Text to scan (typically the managed region extract, not
            the full file).
        start: Absolute offset in `content` where scanning begins.
        terminator_pattern: Compiled regex matched against individual lines
            via `.match`.

    Returns:
        Absolute offset of the first terminator line, or `len(content)` if
        none found.
    """
    pos = start
    while pos < len(content):
        nl = content.find("\n", pos)
        if nl == -1:
            line = content[pos:]
            line_end = len(content)
        else:
            line = content[pos:nl]
            line_end = nl + 1

        if terminator_pattern.match(line):
            return pos

        pos = line_end

    return len(content)


def _find_declared_end_offset(content: str, start: int, literal: str) -> Optional[int]:
    """
    Find the offset of the first line that IS `literal`, scanning from `start`.

    Line-anchored, and deliberately NOT a bare `find()`. `extract_managed_region`
    can use a bare find because the managed region holds only plugin-generated
    content, and its docstring states that guarantee. The pinned region does NOT
    have it, because a user writes the pins. Measured on a pin whose body quotes
    the marker mid-line: a bare find reports a 30-character body and LOSES a pin,
    where a line-wise compare reports 118 and keeps them all.

    TRAILING WHITESPACE IS TOLERATED. LEADING WHITESPACE IS NOT. That asymmetry
    is the whole correctness argument of this function, so do not "tidy" it into
    a `.strip()`:

      - `_find_terminator_offset` matches the RAW line via `.match`, so it does
        not match an indented marker line.
      - A `.strip()` compare here WOULD match one. The two locators then
        disagree about which line ends the region, the declared offset lands
        INSIDE the pinned body, and the region TRUNCATES.
      - Measured, on a document whose first pin quotes the marker on an indented
        line: `.strip()` reports 1 pin where the current parse reports 2.
        `.rstrip()` reports 2. A dropped pin is a cap that fails OPEN.

    THE SIBLING PREDICATES IN `pin_markers` USE `.strip()` AND THAT IS CORRECT
    THERE, which is exactly why this one is easy to get wrong.
    `marker_line_present` and `_is_already_marked` decide whether to REFUSE a
    write, so over-matching costs a skipped write and is fail-SAFE. This
    function decides where a cap stops counting, so over-matching drops a pin
    out of the counted span and is fail-OPEN. Same-looking predicates, OPPOSITE
    failure directions.

    A PREDICATE'S TOLERANCE IS SET BY ITS FAILURE DIRECTION, NEVER BY SYMMETRY
    WITH A PREDICATE THAT LOOKS LIKE IT.

    HOW THIS NEARLY WENT WRONG, recorded because the mechanism is the reusable
    part. `.strip()` was not chosen here carelessly. The argument FOR it is
    written out in `_is_already_marked`'s docstring -- careful and measured, 6
    of 6 against byte-exact's 3 of 6 -- and it was carried across to this
    function. IT IS A CORRECT ARGUMENT ABOUT A DIFFERENT QUESTION. A docstring
    states its conclusion out loud and leaves its premise implicit, so reasoning
    lifted out of one arrives without the condition that made it true. The
    premise there is "a match REFUSES a write". Here a match BOUNDS a region,
    and the conclusion inverts with the premise.

    THE SYMMETRY ERROR RUNS BOTH WAYS, so do not correct it in the other
    direction either: having made THIS locator strict, do NOT go and tighten
    the certificate's presence check to match. That check should stay
    `.strip()`. Over-detection there refuses a write, which is the safe side.
    Two policies, on purpose. Unifying them breaks one of the two, whichever
    way you unify.

    Args:
        content: Text to scan (typically the managed region extract).
        start: Offset in `content` where scanning begins.
        literal: The exact marker text the line must carry.

    Returns:
        Offset of the first matching line, or None when no line matches.
    """
    pos = start
    while pos < len(content):
        nl = content.find("\n", pos)
        if nl == -1:
            line, line_end = content[pos:], len(content)
        else:
            line, line_end = content[pos:nl], nl + 1

        if line.rstrip() == literal:
            return pos

        pos = line_end

    return None


def _parse_pinned_section(content: str) -> Optional[Tuple[int, int, str]]:
    """
    Extract the Pinned Context section from CLAUDE.md content.

    Returns positions in the FULL file content (not managed-region-relative)
    so callers can use them directly for read-mutate-write on the file.

    Round 10 structural guarantee: the parser operates within the
    PACT-managed region only. This region contains only plugin-generated
    content (no user-authored fenced code blocks), so fence-aware scanning
    is unnecessary. If the managed region is not present (pre-migration
    file), falls back to scanning the full content.

    A DECLARED END BOUNDS THE INFERRED ONE. IT NEVER EXTENDS IT:

        inferred   := first terminator line at or after the heading
        declared   := first PINNED_END_MARKER line at or after the heading
        region_end := inferred                      when declared is absent
                   := min(declared, inferred)       otherwise

    THE INVARIANT IS THE WHOLE SAFETY ARGUMENT, and it holds by construction
    rather than by case analysis: `region_end <= inferred` FOR EVERY DOCUMENT.
    `inferred` is what every reader of this region returned before a declared
    end existed, so this parse cannot widen any span, on any input, including
    shapes nobody has enumerated. It can only narrow one.

    THIS IS A NO-OP ON EVERY DOCUMENT CARRYING THE CANONICAL MARKER NAME, and
    that is by design rather than by accident. `PINNED_END_MARKER` carries the
    `PACT_MEMORY_` prefix, so the inferred scan already stops at its line and
    the two offsets coincide. Measured across eleven document shapes, the
    declared and inferred parses agree in every one. The declared parse earns
    its place against a RENAME: take the marker out of the boundary family and
    the inferred scan overruns it and charges the marker text, while this parse
    still excludes it. That is the only shape where the two differ.

    UNMARKED AND HALF-MARKED FILES FAIL OPEN TO THE INFERRED SCAN. No marker at
    all, or a START with no END, is a correct and expected state -- not an
    error, not an incomplete write, not a repair opportunity. Such a document
    parses exactly as it did before this pair existed, and nothing here raises.

    OVER-REACH IS UNREPRESENTABLE RATHER THAN DETECTED, and that distinction is
    worth the sentence. A foreign section between the body and a declared end --
    a heading OR a PACT boundary comment -- stops the inferred scan, so `min`
    takes the inferred offset and the foreign section stays out. No clause
    enumerates those shapes, so no clause can enumerate them too narrowly.

    AN EARLIER REVISION DID ENUMERATE THEM, with a gate that probed for H1/H2
    headings only while the scan also matched the boundary-comment alternation.
    It therefore caught the heading shapes and missed the boundary ones, and
    shipped a cardinal over-block: a boundary comment between the pins and the
    declared end was swallowed into the last pin, which crossed the size cap and
    denied edits that had previously passed. THE LESSON IS ABOUT THE FORM, NOT
    THE ALPHABET -- widening the gate's pattern would have fixed those cases and
    left the same shape of defect available to the next person who edited either
    pattern. A bounded operator has no alphabet to get wrong.

    `_find_declared_end_offset` still matters and covers a DIFFERENT hazard:
    it refuses an indented marker line, so a marker quoted inside a pin body
    cannot become the declared end at all. Read its docstring before changing
    it -- its whitespace policy is deliberately stricter than the certificate's,
    and the two must not be unified.

    Args:
        content: Full CLAUDE.md file content.

    Returns:
        Tuple of (pinned_start, pinned_end, pinned_content) or None if
        no Pinned Context section exists or it is empty. Offsets are
        absolute positions in the original `content` string.
    """
    # Bound to managed region if available (round 10). Offset adjustment
    # converts managed-region-relative positions back to full-file positions.
    region_result = extract_managed_region(content)
    if region_result is not None:
        scan_text, offset = region_result
    else:
        scan_text, offset = content, 0

    pinned_match = re.search(r'^## Pinned Context\s*\n', scan_text, re.MULTILINE)
    if not pinned_match:
        return None

    pinned_start = pinned_match.end()

    # Find the end of pinned section (next H1/H2 heading, or a plugin-managed
    # boundary marker — PACT_MEMORY_, PACT_MANAGED_, PACT_ROUTING_ — or end
    # of scan region). No fence-awareness needed — managed region contains
    # only plugin-generated content (round 10 structural guarantee).
    next_section_pattern = re.compile(
        rf'(?:#{{1,2}}\s|<!-- (?:{_BOUNDARY_ALT}))'
    )
    pinned_end = _find_terminator_offset(
        scan_text, pinned_start, next_section_pattern
    )

    # THE DECLARED END IS A CEILING, NOT AN OVERRIDE. Absent marker ->
    # `declared_end` is None and the inferred scan stands unchanged.
    declared_end = _find_declared_end_offset(
        scan_text, pinned_start, PINNED_END_MARKER
    )
    if declared_end is not None:
        # `min(declared, inferred) <= inferred` FOR EVERY INPUT, and `inferred`
        # is the extent every reader had before a declared end existed. So this
        # parse can never return a span LARGER than the one the scan already
        # produced -- for any document, including shapes nobody has enumerated.
        # A declared end can only ever pull the boundary IN.
        #
        # THAT IS WHY THERE IS NO WELL-FORMEDNESS GATE. A gate DETECTS
        # over-reach; a ceiling makes it UNREPRESENTABLE. Each malformed shape
        # the gate used to name now falls out of the arithmetic instead of
        # needing a clause: an interloping heading or boundary comment stops the
        # inferred scan early, so `min` takes the inferred offset and the foreign
        # section stays out. Nothing here enumerates what "malformed" means, so
        # nothing here can enumerate it too narrowly.
        #
        # THE RENAME ARM IS THIS LINE, not a case beside it. A marker renamed out
        # of the boundary family is not matched by the scan, so the inferred scan
        # overruns it and `inferred > declared`; the `min` then selects the
        # declared offset and the marker text stays out of the body. Excluding it
        # is the only measured difference between the declared and inferred
        # parses, and this operator is what produces it.
        #
        # WHAT STOOD HERE BEFORE WAS A GATE WHOSE PROBE ALPHABET WAS NARROWER
        # THAN THIS SCAN'S. It probed `#{1,2}\s` while the scan also matches the
        # boundary-comment alternation, so a boundary comment between the body
        # and the declared end did not trip it, the declared offset won
        # unbounded, and the region over-reached -- charging PACT's own text into
        # the last pin and denying edits that previously passed. The comment
        # defending it argued that such a comment "already stopped the inferred
        # scan, so pinned_end is at or before it either way". The inferred scan
        # does stop earlier. The branch that sentence guarded then DISCARDED that
        # value and substituted the declared one, which is exactly what "either
        # way" denies. It reasoned from the pre-override world inside the code
        # performing the override.
        pinned_end = min(pinned_end, declared_end)

    pinned_content = scan_text[pinned_start:pinned_end]
    if not pinned_content.strip():
        return None

    return pinned_start + offset, pinned_end + offset, pinned_content


def detect_stale_entries(
    pinned_content: str,
) -> List[Tuple[int, str, str]]:
    """
    Detect stale pinned context entries without modifying them.

    A pinned entry is stale if it contains a date (in a merged-PR reference
    or as a standalone YYYY-MM-DD) older than PINNED_STALENESS_DAYS, and
    has not already been marked with a STALE comment.

    Args:
        pinned_content: The text of the Pinned Context section (after the
            ## heading).

    Returns:
        List of (entry_index, date_string, entry_heading) tuples for each
        stale entry found. entry_index is the position within entry_starts.
    """
    entry_pattern = re.compile(r'^### ', re.MULTILINE)
    entry_starts = [m.start() for m in entry_pattern.finditer(pinned_content)]

    if not entry_starts:
        return []

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=PINNED_STALENESS_DAYS)

    # Pattern to match "PR #NNN, merged YYYY-MM-DD" in entry text
    pr_merged_pattern = re.compile(
        r'PR\s*#\d+,?\s*merged\s+(\d{4}-\d{2}-\d{2})'
    )
    # Fallback: any standalone YYYY-MM-DD date in the entry header line
    standalone_date_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})')
    # Pattern to detect existing staleness marker
    stale_marker_pattern = re.compile(r'<!-- STALE: Last relevant \d{4}-\d{2}-\d{2} -->')

    stale_entries: List[Tuple[int, str, str]] = []

    for i, start in enumerate(entry_starts):
        if i + 1 < len(entry_starts):
            end = entry_starts[i + 1]
        else:
            end = len(pinned_content)

        entry_text = pinned_content[start:end]

        # Skip entries already marked stale
        if stale_marker_pattern.search(entry_text):
            continue

        # Extract the heading line for context
        nl_pos = entry_text.find("\n")
        heading = entry_text[:nl_pos] if nl_pos != -1 else entry_text

        # Look for PR merged date first (most specific)
        date_str = None
        pr_match = pr_merged_pattern.search(entry_text)
        if pr_match:
            date_str = pr_match.group(1)
        else:
            # Fallback: find any YYYY-MM-DD date in the heading line
            date_match = standalone_date_pattern.search(heading)
            if date_match:
                date_str = date_match.group(1)

        if not date_str:
            continue

        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if entry_date < stale_threshold:
            stale_entries.append((i, date_str, heading))

    return stale_entries


def apply_staleness_markings(
    content: str,
    pinned_start: int,
    pinned_end: int,
    pinned_content: str,
) -> Tuple[str, int, bool, str]:
    """
    Apply stale markers and budget warnings to pinned content.

    Detects stale entries, inserts STALE markers, and rewrites the budget
    warning comment to match the CURRENT content. Returns the modified full
    file content.

    THE WARNING IS REBUILT FROM THE BODY ON EVERY PASS, NEVER PATCHED IN PLACE.
    An earlier warning is removed first, the warning-free body is measured, and
    a fresh line goes back only when the measurement still exceeds the budget.

    Three properties follow from that order, and they are the whole reason for
    it:

      - THE NUMBER CANNOT GO STALE. It is recomputed against whatever the body
        holds now, so it tracks a growing or shrinking pinned section.
      - THE WARNING CANNOT INFLATE ITS OWN COUNT. The measured body never
        contains the warning at the HEAD, on pass 1 or pass 500, so the number
        does not creep upward as the report of it is re-read. A warning a user
        has moved below the head IS measured, and it is a FIXED contribution:
        this module writes only at the head, and the head is taken back before
        each measurement, so no pass can add a second one.
      - THE PASS IS IDEMPOTENT BY CONSTRUCTION, not by a guard. The emitted line
        is a pure function of the user's pinned body, so a second pass over
        unchanged pins produces identical bytes and writes nothing.

    A BODY THAT DROPS BACK UNDER BUDGET LOSES ITS WARNING. A warning that
    reports a breach which has ended is the same defect as a frozen number,
    facing the other way. Removing it is a REPAIR of a line this module wrote,
    which is why it is safe; this function never deletes anything a user wrote.

    Args:
        content: Full CLAUDE.md file content.
        pinned_start: Start offset of pinned section body in content.
        pinned_end: End offset of pinned section body in content.
        pinned_content: The pinned section body text.

    Returns:
        Tuple of (new_full_content, stale_count, was_modified, budget_warning_str).
    """
    # The bytes to compare against at the end. `was_modified` is DERIVED from
    # this comparison rather than accumulated in a flag, so it cannot disagree
    # with what actually changed -- and a pass that rewrites a warning to the
    # same value reports no modification and skips the write.
    original_pinned_content = pinned_content

    # STEP 1, BEFORE ANY OFFSET IS TAKEN OR ANY TOKEN IS COUNTED: take back the
    # warning written by an earlier pass. Every step below then sees the user's
    # own pinned body. Order is load-bearing -- `entry_starts` holds offsets
    # into this string, so a later strip would invalidate them.
    pinned_content = _strip_budget_warnings(pinned_content)

    entry_pattern = re.compile(r'^### ', re.MULTILINE)
    entry_starts = [m.start() for m in entry_pattern.finditer(pinned_content)]
    stale_marker_pattern = re.compile(r'<!-- STALE: Last relevant \d{4}-\d{2}-\d{2} -->')

    # Count already-marked entries
    already_stale = 0
    for i, start in enumerate(entry_starts):
        end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(pinned_content)
        entry_text = pinned_content[start:end]
        if stale_marker_pattern.search(entry_text):
            already_stale += 1

    # Detect new stale entries
    stale_entries = detect_stale_entries(pinned_content)

    # Apply stale markers in reverse order so string offsets remain valid
    for idx, date_str, _heading in reversed(stale_entries):
        start = entry_starts[idx]
        end = entry_starts[idx + 1] if idx + 1 < len(entry_starts) else len(pinned_content)
        entry_text = pinned_content[start:end]

        stale_marker = f"<!-- STALE: Last relevant {date_str} -->\n"
        nl_pos = entry_text.find("\n")
        if nl_pos == -1:
            # Entry is a single line with no newline; skip it
            continue
        heading_end = nl_pos + 1
        new_entry = entry_text[:heading_end] + stale_marker + entry_text[heading_end:]
        pinned_content = pinned_content[:start] + new_entry + pinned_content[end:]

    total_stale = already_stale + len(stale_entries)

    # Measure the body with the HEAD warning taken back. Step 1 removes the
    # leading run on every pass and not only on the first one, which is the
    # hazard the old presence guard reached for and missed. A warning a user has
    # moved below the head is NOT removed and IS measured. That is the accepted
    # residual.
    pinned_tokens = estimate_tokens(pinned_content)
    budget_warning = ""
    if pinned_tokens > PINNED_CONTEXT_TOKEN_BUDGET:
        pinned_content = (
            f"{_BUDGET_WARNING_PREFIX} ~{pinned_tokens} tokens "
            f"(budget: {PINNED_CONTEXT_TOKEN_BUDGET}). "
            f"Consider archiving stale pins. -->\n"
        ) + pinned_content
        # ONE number, used by both consumers. The comment in the file and the
        # status string returned to the caller are built from the same
        # measurement, so a reader can never be shown two different figures for
        # one document.
        budget_warning = f", ~{pinned_tokens} tokens (budget: {PINNED_CONTEXT_TOKEN_BUDGET})"

    # Under budget, the body simply keeps no warning: the strip in step 1 has
    # already taken the outdated one away, and nothing puts it back.

    modified = pinned_content != original_pinned_content
    new_content = content[:pinned_start] + pinned_content + content[pinned_end:]
    return new_content, total_stale, modified, budget_warning


def check_pinned_staleness(claude_md_path: Optional[Path] = None) -> Optional[str]:
    """
    Detect stale pinned context entries in the project CLAUDE.md.

    A pinned entry is considered stale if it contains a date older than
    PINNED_STALENESS_DAYS. Dates are detected in PR merge references
    (e.g. "PR #123, merged 2026-01-15") and as standalone YYYY-MM-DD
    patterns in entry headings.

    Stale entries get a <!-- STALE: Last relevant YYYY-MM-DD --> comment
    inserted after their heading (if not already marked).

    Also checks if the total pinned content exceeds the token budget and
    adds a warning comment if so (does NOT auto-delete pins).

    This function orchestrates detection (detect_stale_entries) and
    mutation (apply_staleness_markings) as separate steps for testability.

    Args:
        claude_md_path: Explicit path to CLAUDE.md. If None, resolved via
            get_project_claude_md_path(). Callers (e.g. session_init.py)
            may pass the path explicitly so their own resolution can be
            patched independently in tests.

    Returns:
        Informational message about stale pins found, or None.
    """
    if claude_md_path is None:
        claude_md_path, project_root = _resolve_project_claude_md_with_base()
    else:
        # A caller-supplied path came from a TRUSTED resolver -- session_init
        # resolves via _get_project_claude_md_path() and PASSES it here, so
        # production DOES supply the param. Recover its pre-.claude base by
        # inverting the resolver's construction (see _lexical_base_of): the
        # SAME base the resolver used, not a re-derived root, and F1-safe
        # (purely lexical, no symlink follow) + parity-locked.
        project_root = _lexical_base_of(claude_md_path)
    if claude_md_path is None:
        return None

    try:
        content = claude_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    parsed = _parse_pinned_section(content)
    if parsed is None:
        return None

    pinned_start, pinned_end, pinned_content = parsed

    entry_pattern = re.compile(r'^### ', re.MULTILINE)
    entry_starts = [m.start() for m in entry_pattern.finditer(pinned_content)]

    # A section with no entries still needs a pass when a warning is sitting in
    # it. Delete the last pin and the old guard returned here, which stranded
    # that warning where nothing could ever reach it.
    #
    # THE PROBE READS ANY LINE START, THE STRIP READS OFFSET 0. That gap is
    # deliberate. A warning a user has moved below the head is still this
    # module's own report, so the section HAS been reported on and the pass may
    # run. The strip cannot reach that line, so this pass does not repair it: it
    # adds one current warning above it and the old line stays. That is the
    # ratified cost of the residual, one extra line, and it is what a section
    # WITH entries already does in the same state.
    #
    # THE FORBIDDEN DIRECTION IS UNCHANGED AND MUST STAY SO. A section carrying
    # NO line of this module's own shape never reaches the pass, whatever its
    # size, so this code never starts a report in a document it has not written
    # to before. The strict `~N tokens (budget: M)` shape carries that
    # discrimination, not the anchor.
    if not entry_starts and not _has_budget_warning(pinned_content):
        return None

    new_content, stale_count, modified, budget_warning = apply_staleness_markings(
        content, pinned_start, pinned_end, pinned_content
    )

    # Write back if modified — under file_lock with TOCTOU symlink guard.
    # staleness.py is the 6th writer to project CLAUDE.md and must use the
    # same hardening as the other 5 (claude_md_manager + session_resume).
    # See `fcntl_sidecar_lock_pattern` for the canonical pattern.
    if modified:
        try:
            # Function-level import to avoid circular dependency:
            # session_init.py imports staleness at module level, and also
            # imports from shared.claude_md_manager — a module-level
            # import here would create a staleness → claude_md_manager →
            # (indirectly) staleness cycle on some Python versions.
            from shared.claude_md_manager import (
                ContainmentError,
                _atomic_write_text,
                file_lock,
            )
            with file_lock(claude_md_path):
                # #1247: containment (in _atomic_write_text) REPLACES the
                # former leaf is_symlink guard -- inside the lock (TOCTOU-safe).
                # It catches the symlinked-PARENT escape the leaf guard MISSED
                # (F1) and safely ALLOWS a benign in-project leaf redirect; it
                # does NOT dominate is_symlink (overlapping-but-different sets).
                # Status string stays opaque.
                # Re-read inside the lock — a concurrent update_session_info
                # may have landed between our outer
                # read at L348 and the lock acquisition. If content changed,
                # skip this pass: the staleness markers are idempotent and
                # the next session will re-detect any stale entries. This
                # avoids clobbering a concurrent writer's SESSION_START block.
                current = claude_md_path.read_text(encoding="utf-8")
                if current != content:
                    return None
                # Atomic (temp + rename) so a crash mid-write cannot truncate
                # the always-loaded CLAUDE.md. NOTE: unlike the other CLAUDE.md
                # write sites this one never set a mode, so `write_text` left
                # the file's existing permissions alone; the helper normalises
                # it to 0o600, matching every other writer in the plugin.
                _atomic_write_text(claude_md_path, new_content, project_root)
        except ContainmentError:
            return "Pinned staleness skipped: path precondition not met."
        except TimeoutError:
            return "Pinned staleness update skipped: lock contention."
        except OSError as e:
            # Truncate like the sibling write sites (session_resume, cli): the
            # raw exception embeds the absolute CLAUDE.md path, which should not
            # leak into a status string.
            logger_msg = f"Failed to update pinned staleness: {str(e)[:50]}"
            return logger_msg

    if stale_count > 0:
        return f"Pinned context: {stale_count} stale pin(s) detected{budget_warning}"
    if budget_warning:
        return f"Pinned context{budget_warning}"

    return None


def check_pinned_block_signal(
    claude_md_path: Optional[Path] = None,
) -> Optional[CapViolation]:
    """Detect stale-pin overflow that warrants a SessionStart block directive.

    Returns a CapViolation(kind=\"stale\") when the stale pin count meets or
    exceeds PIN_STALE_BLOCK_THRESHOLD; None otherwise. Caller (session_init)
    emits an unconditional directive in additionalContext on positive
    detection — never exit-2 (would break /clear and /resume per plan
    key-decisions row 6).

    Fail-open: all I/O and parse errors yield None. The block directive
    ONLY fires on positive detection; ambiguous state never blocks.

    Args:
        claude_md_path: Explicit path. If None, resolved via
            get_project_claude_md_path(). Callers may patch resolution
            independently from this module.

    Returns:
        CapViolation describing the stale overflow, or None.
    """
    if claude_md_path is None:
        claude_md_path = _get_project_claude_md_path()
    if claude_md_path is None:
        return None

    try:
        content = claude_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    parsed = _parse_pinned_section(content)
    if parsed is None:
        return None

    _, _, pinned_content = parsed

    try:
        pins = parse_pins(pinned_content)
    except Exception:  # noqa: BLE001 — fail-open by construction
        return None

    return check_stale_block(pins, threshold=PIN_STALE_BLOCK_THRESHOLD)
