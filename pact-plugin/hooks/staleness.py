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

# H1/H2 heading only, WITHOUT the boundary-marker alternation. Used by the
# well-formedness gate in _parse_pinned_section, which asks a narrower question
# than the terminator scan does: "does a foreign SECTION begin before the
# declared end". A PACT boundary comment is not a foreign section, and folding
# one in here would refuse the declared end on documents where the pair is
# perfectly well formed.
_HEADING_ONLY = re.compile(r'#{1,2}\s')


# Staleness detection constants

# Number of days after which a pinned entry referencing a merged PR is
# considered stale and gets an HTML comment marker.
PINNED_STALENESS_DAYS = 30

# Approximate token budget for the entire Pinned Context section. When
# exceeded, a warning comment is added (no auto-deletion).
# This is the sole definition of this constant; session_init.py imports it.
PINNED_CONTEXT_TOKEN_BUDGET = 1200


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

    THE END OF THE REGION IS DECLARED WHEN A MARKER SAYS SO, AND INFERRED
    OTHERWISE:

        inferred   := first terminator line at or after the heading
        declared   := first PINNED_END_MARKER line at or after the heading
        region_end := inferred   when declared is absent
                   := inferred   when an H1/H2 heading lies before declared
                   := declared   otherwise

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

    THE H1/H2 GATE GUARDS OVER-REACH, WHICH IS THE DIRECTION A MATCHED MARKER
    MAKES REACHABLE. A foreign `## Interloper` section between the body and a
    declared end would otherwise be pulled INTO the pinned span by the declared
    offset. Note what the gate does NOT cover: a `### ` pin heading is not H1 or
    H2, so a marker quoted inside a pin body reaches the declared offset with no
    heading in front of it. `_find_declared_end_offset` is what covers that, by
    refusing to match an indented line -- read its docstring before changing
    either mechanism, because they cover adjacent halves of one hazard.

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

    # The declared end overrides the inferred one, subject to the gate below.
    # Absent marker -> `declared_end` is None and the inferred scan stands.
    declared_end = _find_declared_end_offset(
        scan_text, pinned_start, PINNED_END_MARKER
    )
    if declared_end is not None:
        # WELL-FORMEDNESS GATE. An H1 or H2 heading between the body start and
        # the declared end means the pair straddles a section boundary. The
        # pairing is MALFORMED, and honouring the declared offset would swallow
        # that foreign section into the pinned span. Keep the inferred scan.
        #
        # The probe is bounded to `scan_text[:declared_end]`, so a miss returns
        # that slice's length, which IS `declared_end` -- hence `>=` reads as
        # "no heading found before the declared end".
        #
        # The probe pattern is H1/H2 ONLY, not the full terminator alternation.
        # A PACT boundary comment before the declared end already stopped the
        # inferred scan, so `pinned_end` is at or before it either way and the
        # gate has nothing left to decide.
        heading_before_declared = _find_terminator_offset(
            scan_text[:declared_end], pinned_start, _HEADING_ONLY
        )
        if heading_before_declared >= declared_end:
            pinned_end = declared_end
        # else: MALFORMED. `pinned_end` keeps the inferred offset untouched.
        # That offset is provably at or before the interloping heading, because
        # the inferred alternation matches H1/H2 too, so no clamp is needed here
        # and a `min()` would be a no-op dressed as a safeguard.

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

    Detects stale entries, inserts STALE markers, and adds a budget
    warning comment if the content exceeds the token budget. Returns the
    modified full file content.

    Args:
        content: Full CLAUDE.md file content.
        pinned_start: Start offset of pinned section body in content.
        pinned_end: End offset of pinned section body in content.
        pinned_content: The pinned section body text.

    Returns:
        Tuple of (new_full_content, stale_count, was_modified, budget_warning_str).
    """
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
    modified = False

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
        modified = True

    total_stale = already_stale + len(stale_entries)

    # Check token budget BEFORE inserting the warning (so warning text
    # does not inflate its own count)
    pinned_tokens = estimate_tokens(pinned_content)
    budget_warning = ""
    if pinned_tokens > PINNED_CONTEXT_TOKEN_BUDGET:
        budget_warning_comment = (
            f"<!-- WARNING: Pinned context ~{pinned_tokens} tokens "
            f"(budget: {PINNED_CONTEXT_TOKEN_BUDGET}). "
            f"Consider archiving stale pins. -->\n"
        )
        # Add budget warning at the top of pinned section if not present
        if "<!-- WARNING: Pinned context" not in pinned_content:
            pinned_content = budget_warning_comment + pinned_content
            modified = True
        budget_warning = f", ~{pinned_tokens} tokens (budget: {PINNED_CONTEXT_TOKEN_BUDGET})"

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
    if not entry_starts:
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
