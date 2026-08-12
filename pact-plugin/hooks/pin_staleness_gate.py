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
  3. Edit locus is within the Pinned Context section (line-bounded)
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
PIN_STALENESS_MARKER_NAME = "pin-staleness-pending"

_DENY_REASON = (
    "Pinned Context edits are gated: stale pins detected. "
    "Run /PACT:pin-memory to archive stale pins before editing "
    "the ## Pinned Context section of CLAUDE.md."
)

_GATED_TOOLS = frozenset({"Edit", "Write"})


# A heading a memory writer emits. `working_memory.py` builds each one as
# `f"### {date_str}"` with `date_str = now.strftime("%Y-%m-%d %H:%M")`, so the
# shipped shape is a date and a time. The time is optional here so a
# hand-written date-only entry is covered too.
#
# THE PATTERN IS DERIVED FROM THE WRITERS AND NOT FROM A READING OF THIS FILE.
# A pattern written against a guess passes a test written against the same
# guess. `tests/test_working_memory.py` pins the emitted format, and that arm
# lives with the WRITERS, because a person who edits a writer does not read the
# tests of this gate.
_DATE_LED_HEADING_RE = re.compile(
    r"^###\s+\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?\s*$"
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

    A GUARD ON THE MARKER-ADDING EDIT WAS CONSIDERED AND REFUSED. See the
    design ruling: a guard for R2 cannot separate the marker-adding edit from a
    real add without reading the file the edit has not landed in yet, which
    makes a string comparison race a file it does not own.
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

    THE SLICE NOW BELONGS TO THE DECISION, in `_is_add_shaped_edit`, which is
    the only place that can see the two sides at one time. This function counts
    across the body its caller supplies and nothing else.

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
      1. Ask each side whether it carries the managed markers.
      2. If the two agree, use that branch for the two.
      3. If the two disagree, use the WHOLE TEXT for the two.
    The whole text is a slice each side can always carry, so there is no
    failure direction to choose here and no exception arm to add.

    🔴 THE WHOLE-TEXT FALLBACK KEEPS THE MEMORY ENTRIES. `_is_memory_entry` IS
    WHAT DROPS THEM. DO NOT REMOVE THE DATE-LED EXCLUSION AND KEEP THIS
    FALLBACK: the pair is correct and each one alone is worse than the pair.
    Measured, the wider slice alone re-introduces the over-count this repair
    exists to remove.

    THE EXCEPTION BEHAVIOUR IS UNCHANGED. This selects a slice. The fail-open
    arms that the caller declares SACROSANCT stay where they are.
    """
    from shared.claude_md_manager import extract_managed_region

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
