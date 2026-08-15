"""
Working Memory Sync Module

Location: pact-plugin/skills/pact-memory/scripts/working_memory.py

Summary: Handles synchronization of memories to the Working Memory section
in CLAUDE.md. Maintains a rolling window of the most recent memories for
quick reference during Claude sessions. Applies token budgets to prevent
unbounded growth of memory sections.

Used by:
- memory_api.py: Calls sync_to_claude_md() after saving memories
- Test files: test_working_memory.py tests all functions in this module
"""

from __future__ import annotations

import fcntl
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Constants for working memory section (saved memories).
# Working Memory provides structured, PACT-specific context (goals, decisions,
# lessons) synced from the SQLite database. It coexists with the platform's
# auto-memory (MEMORY.md), which captures free-form session learnings. Reduced
# from 5 to 3 entries to limit token overlap between the two systems while
# retaining the structured format that auto-memory does not provide.
WORKING_MEMORY_HEADER = "## Working Memory"
# THE COUNT CLAUSE WAS REMOVED BECAUSE IT WAS FALSE IN THE COMMON REGIME, NOT
# BECAUSE IT WAS UNTIDY. `_apply_token_budget` never compresses `entries[0]`
# and its drop loop is `while len(result) > 1`, so when the newest entry ALONE
# exceeded the whole-section budget the older entries were dropped and the
# section showed ONE entry. This string is written INTO the artifact it
# describes, so every agent loading a CLAUDE.md read the false claim inline,
# beside a section that often held a single entry.
#
# THAT ONE-ENTRY REGIME IS NOW CLOSED, AND THE COUNT CLAUSE STAYS OUT ANYWAY.
# `_apply_entry_token_ceiling` bounds each entry so that the newest one
# cannot exhaust the section alone, and the per-field character bound in
# `_format_memory_entry` puts a typical full entry far below the budget. A
# fixed count is still the wrong thing to promise: the cap is a CAP, the
# store can hold fewer entries than it, and a promise here would go stale the
# next time either bound moves.
#
# WHAT REPLACED IT IS UNCONDITIONAL. The searchability clause is TRUE in every
# regime and is kept: it is the clause that tells a reader where the durable
# copy lives. Deleting the whole comment would have removed a true, useful
# statement along with the false one.
#
# DO NOT "RESTORE" A COUNT, and do not replace it with "entries are not
# addressable by ID" either -- that is a NEW false claim in the other
# direction, because only OLDER entries lose their ID. The newest entry is
# always full and always carries its Memory ID.
#
# MIRRORED IN TWO OTHER DEFINITIONS -- `hooks/shared/session_resume.py` and
# `hooks/shared/claude_md_manager.py`. Change all three in ONE commit: fixing
# two of three converts one consistent falsehood into a three-way disagreement.
WORKING_MEMORY_COMMENT = "<!-- Auto-managed by pact-memory skill. Full history searchable via pact-memory skill. -->"
MAX_WORKING_MEMORIES = 3

# Constants for retrieved context section (searched/retrieved memories)
RETRIEVED_CONTEXT_HEADER = "## Retrieved Context"
RETRIEVED_CONTEXT_COMMENT = "<!-- Auto-managed by pact-memory skill. Last 3 retrieved memories shown. -->"
MAX_RETRIEVED_MEMORIES = 3

# Token budget constants.
# Approximation: 1 token ~ 0.75 words, so word_count * 1.3 ~ token count.
WORKING_MEMORY_TOKEN_BUDGET = 800
RETRIEVED_CONTEXT_TOKEN_BUDGET = 500
# Note: PINNED_CONTEXT_TOKEN_BUDGET is defined solely in hooks/staleness.py

# Maximum characters `_compress_memory_entry` keeps of a summary before it
# appends "...". NAMED BECAUSE THE BARE LITERAL HAD A DECOY. This value was
# spelled 120 at five sites in `_compress_memory_entry`, while
# OVERRIDE_RATIONALE_MAX below is a DIFFERENT 120 that bounds an override
# rationale. A reader who greps the literal to find the source of the
# compressed-entry arithmetic can bind to the override cap, and the two
# values AGREE, so nothing goes red and the mistake is invisible. The name
# is the fix: COMPRESSED_ENTRY_TOKEN_CEILING derives from THIS constant.
COMPRESSED_SUMMARY_CHAR_CAP = 120

# Token cost of ONE compressed neighbour, at its maximum.
#
# THIS IS AN ESTIMATE AND IT IS LABELLED ONE DELIBERATELY. It rests on
# THREE premises, and a change to any of them moves it: the summary cap is
# COMPRESSED_SUMMARY_CHAR_CAP plus the 3 characters of the truncation
# marker; a memory id is bounded at _REFRESH_IDENTIFIER_TRUNCATION_LIMIT
# characters; and the worst-case density is 2 characters for each word
# ROUNDED DOWN, which is one character plus one space and is the densest
# input `str.split()` can meet. THE DIRECTION OF THE ROUND IS PART OF THE
# RULE AND IT IS REPEATED AT EACH RESTATEMENT, because a reader who meets
# this premise alone would otherwise hold the rule without its direction.
#
# COUNTING RULE, AND IT STATES ITS ROUNDING BECAUSE THE ARITHMETIC IS ODD:
# measure the ASSEMBLED three-line compressed form, being the date header,
# the `**Summary**` line at the cap, and the `**Memory ID**` line. At 2
# characters for each word, ROUNDED DOWN, 123 characters gives 61 words
# rather than 61.5. A reader who rounds UP reproduces none of the numbers
# here, so the direction is part of the rule. MEASURED: 128.
#
# THE VARIABLE IS DENSITY AND NOT LENGTH, WHICH IS THE WHOLE CAUSE OF THIS
# CONSTANT MOVING. A character bound cannot enforce a token budget, because
# the producer of the value controls the ratio. At the 64-character
# identifier bound, a DENSE id costs 128 and a one-token id costs 88, from
# the same character count. The 128 is the dense case, so the bound holds
# for the adversarial shape rather than for the friendly one.
#
# DO NOT DERIVE THIS BY ADDING PARTS. The estimator applies `int()` ONCE
# to the word count of the WHOLE string, so two separately rounded parts
# do not sum to the rounded whole.
#
# This is the per-entry cost the SITE A ceiling reserves for the two
# neighbours it compresses; see `_apply_token_budget`.
COMPRESSED_ENTRY_TOKEN_CEILING = 128

# Pin caps constants (twin copy of hooks/pin_caps.py — cannot import across
# the skills-to-hooks package boundary). Drift-detection test in
# tests/test_staleness.py guards against divergence; if you change these,
# update hooks/pin_caps.py in the SAME commit.
#
# Forward-looking drift anchors: no skill-side code currently consumes these
# constants — they exist here solely so a future skills-side pin-cap
# consumer can read the budget without needing to cross the package
# boundary. Anchored only by TestPinCapsTwinCopyDrift. Do NOT remove
# even if unused at read time; the drift test + forward-compat intent are
# the justification for the twin copy.
PIN_COUNT_CAP = 12
PIN_SIZE_CAP = 1500
PIN_STALE_BLOCK_THRESHOLD = 2
OVERRIDE_RATIONALE_MAX = 120

# PACT-managed boundary marker prefixes. Used by _find_terminator_offset to
# terminate section scans on any PACT boundary marker. The canonical
# definition lives in hooks/shared/claude_md_manager.py as
# PACT_BOUNDARY_PREFIXES — this module cannot import from hooks/shared/
# (separate package boundary), so the alternation is inlined here. The
# three prefixes rarely change; if a 4th is added, update this string.
_PACT_BOUNDARY_ALT = "PACT_MEMORY_|PACT_MANAGED_|PACT_ROUTING_"

# Managed-region boundary markers. Twin copies of the canonical definitions
# in hooks/shared/claude_md_manager.py (cannot import — separate package).
_MANAGED_START_MARKER = "<!-- PACT_MANAGED_START: Managed by pact-plugin - do not edit this block -->"
_MANAGED_END_MARKER = "<!-- PACT_MANAGED_END -->"

# file_lock: vendored twin of hooks/shared/claude_md_manager.file_lock —
# skills/pact-memory/scripts/ cannot import from hooks/shared/ (separate
# package boundary). Cross-process correctness is preserved because
# fcntl.flock serializes on the sidecar inode, not the Python object: a hook
# process and this skill process locking the SAME .{name}.lock sidecar
# contend on the same kernel lock. The drift-detection test
# (TestFileLockTwinCopyDrift in tests/test_staleness.py) guards byte-alignment
# of the function body with the canonical copy; if you change either, update
# both in the SAME commit. The two constants below are part of the twin and
# must match the canonical values.
_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_POLL_INTERVAL = 0.1

# _sanitize_prompt_field: vendored twin of
# hooks/shared/session_resume._sanitize_prompt_field — skills/pact-memory/
# scripts/ cannot import from hooks/shared/ (separate package boundary).
# The drift-detection test (TestSanitizePromptFieldTwinCopyDrift in
# tests/test_staleness.py) guards byte-alignment of the function body with
# the canonical copy; if you change either, update both in the SAME commit.
# The three values below are part of the twin and must match the canonical
# ones, which is what test_sanitize_prompt_field_constants_match asserts.
#
# Bounds for record field values interpolated into the managed regions of
# CLAUDE.md. The store is plain SQLite on disk and a field value is
# caller-influenced, so a hand-crafted or corrupted record must not be able
# to open a heading inside a PACT-managed region or flood the always-loaded
# context. Free-text fields get the tight bound; paths get a wider one
# because legitimate absolute paths can be long.
_REFRESH_FIELD_TRUNCATION_LIMIT = 200
_REFRESH_PATH_TRUNCATION_LIMIT = 512

# IDENTIFIER is a THIRD field kind, and its absence was a defect rather
# than an omission. A memory id took the FREE-TEXT bound of 200, which is
# 3 times what the generator emits and lets one field dominate the token
# cost of a compressed entry. The store does NOT bound this value: the
# ingress validates the KEY SET of a record rather than the length of a
# value, so a caller-supplied id reaches the formatter unbounded.
# 64 covers a 32-character generated id with double the margin.
#
# CLASSIFY BY FIELD KIND, NOT BY DEFAULT. A field with no row in the
# classification falls to free text, and free text is the WIDEST bound, so
# a missing row always errs toward the loose end.
_REFRESH_IDENTIFIER_TRUNCATION_LIMIT = 64

# Control characters collapsed in interpolated field values: C0 controls
# (includes \n, \r, \t), DEL plus the full C1 block (which includes NEL
# U+0085 — a str.splitlines boundary), and the Unicode line/paragraph
# separators — anything that could break a value onto a new line and
# masquerade as a heading or a separate entry.
_PROMPT_CONTROL_CHARS_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]+")


@contextmanager
def file_lock(target_file: Path):
    """Acquire an exclusive sidecar file lock for a target CLAUDE.md path.

    Twin of hooks/shared/claude_md_manager.file_lock — kept local because
    skills/pact-memory/scripts/ cannot import from hooks/shared/. Body MUST
    stay byte-identical to the canonical copy (drift test enforces this).

    NOT RE-ENTRANT: fcntl.flock is non-re-entrant at the OS level. Nesting one
    sync site inside another under the SAME target would self-deadlock until the
    fail-open TimeoutError (after _LOCK_TIMEOUT_SECONDS). This is not reachable
    on the current call graph — the two sync sites are independent top-level
    calls, never nested — so no behavioral re-entrancy guard is added (a guard
    would alter this body and trip the drift test; the OS-level non-re-entrancy
    plus the callers' fail-open already bound the worst case).
    """
    # Key the sidecar on the DIRECTORY THE WRITE BINDS INTO plus the LITERAL
    # leaf name, so lock identity and write identity are the same thing and
    # cannot diverge when the write replaces the leaf entry.
    # The PARENT is resolved so two spellings of one directory produce one
    # sidecar, and therefore one lock. The LEAF is deliberately NOT resolved:
    # os.replace is renameat(2) and binds the final component as a directory
    # ENTRY without following it, so resolving the leaf would key the lock on a
    # path the write never touches -- and would make the key CHANGE across the
    # write, which is a lock whose identity is a function of the state it is
    # supposed to protect. Mirrors the write's own os.open(target.parent) +
    # target.name; see the write-shape dependency noted in _atomic_write_text.
    # NOT provided, deliberately: two NAMES for one INODE do not collapse onto
    # one sidecar. A hardlink pair is exactly that and never collapsed under
    # any spelling of this formula, because resolve() canonicalises symlinks
    # and not inodes -- the justification this comment replaced claimed
    # otherwise and was wrong about its own code.
    lock_path = target_file.parent.resolve() / f".{target_file.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 0o600: the lock file is adjacent to user-private CLAUDE.md content;
    # match the same permissions to avoid leaving a world-readable sidecar.
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    # S8 (security-engineer-review): emit a stderr
                    # warning before raising. Callers fail-open on
                    # TimeoutError (skip the cleanup pass), so without
                    # this warning a stuck holder would silently defer
                    # kernel-block / managed-block cleanup forever.
                    # Stderr from hooks does not surface in the user
                    # transcript, but it does land in Claude Code's
                    # debug logs — repeated warnings make the
                    # contention-vs-bug class observable.
                    print(
                        f"PACT file_lock timeout: failed to acquire "
                        f"lock on {lock_path} within "
                        f"{_LOCK_TIMEOUT_SECONDS}s; falling open",
                        file=sys.stderr,
                    )
                    raise TimeoutError(
                        f"Failed to acquire lock on {lock_path} within "
                        f"{_LOCK_TIMEOUT_SECONDS}s"
                    )
                time.sleep(_LOCK_POLL_INTERVAL)
        yield
    finally:
        # Release before close. flock is released automatically on fd close
        # by the kernel, but an explicit LOCK_UN ensures immediate release
        # even if close is delayed (e.g., by subsequent finalizer work).
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


# Why the sync sites lock the WHOLE read->mutate->write window (not just the
# write). This rationale is shared by both sync_to_claude_md and
# sync_retrieved_to_claude_md, which each carry only a short pointer back here.
# (Distinct from the "why an inline twin" note above: that explains WHY the lock
# is vendored; this explains WHY the lock spans the whole window.)
#   - read-under-lock is the load-bearing no-clobber property: a write-only lock
#     would let a 2nd writer read stale (pre-this-write) content, mutate it, and
#     overwrite this writer's entry the instant the lock releases — the exact
#     lost update the lock exists to prevent.
#   - lock identity is the sidecar inode of the RESOLVED CLAUDE.md path, so this
#     serializes against session_init / session_resume: all writers resolve to
#     the same .claude/CLAUDE.md (CLAUDE_PROJECT_DIR is set every session → all
#     hit the env-var branch first) and thus share one .CLAUDE.md.lock sidecar.
#   - CLAUDE_PROJECT_DIR edge: if it were ever unset AND the git-root/cwd
#     fallbacks diverged between processes, the sidecars would differ and the
#     lock would not serialize — accepted as out-of-contract (no safe fallback
#     action exists if the paths genuinely diverge).


class ContainmentError(OSError):
    """A CLAUDE.md write target escaped its project containment boundary (#1247).

    Subclasses OSError so a caller that does not name it explicitly still
    catches it via `except OSError`. Callers convert it to an OPAQUE skip
    message that does not leak the resolved victim path.

    Twin of ContainmentError in `hooks/shared/claude_md_manager.py` (this module
    cannot import from hooks/shared). The two class defs are trivial markers;
    the load-bearing logic is the containment CHECK inside `_atomic_write_text`,
    drift-gated by TestAtomicWriteTwinCopyDrift.
    """


def _detect_line_ending(name: str, parent_fd: int) -> str:
    """
    Report the line ending `name` uses today, read THROUGH `parent_fd`.

    READ THE BYTES, BECAUSE EVERY TEXT READ HAS ALREADY LOST THE ANSWER.
    `Path.read_text` applies universal-newline translation, so a CRLF file
    arrives as LF and the original ending is unrecoverable from the string a
    caller holds. This is the only place that looks.

    IT TAKES A DESCRIPTOR AND A NAME RATHER THAN A PATH, AND THAT IS THE WHOLE
    POINT OF THE SIGNATURE. `_atomic_write_text` pins the parent directory open
    and binds the write through that descriptor. A read by name inside it would
    reintroduce the name-based race the descriptor design removes, so this
    samples the same kernel object the containment walk approved.

    DOMINANT WINS, AND A TIE GOES TO LF. The write this feeds is unrecoverable,
    because CLAUDE.md is gitignored, so the correct rule is the one that changes
    the fewest lines. Dominant-wins minimises that count by construction. A file
    with no CRLF at all has a dominant of LF, so no file can gain an ending it
    did not have. A file written only with bare carriage returns reports LF.

    A TARGET THAT IS NOT ON DISK REPORTS LF, and that arm is load-bearing rather
    than defensive: it is why file creation is not a gap. A create-only caller
    writes its LF template to a name that is not there, so nothing converts.
    A read failure reports LF for the same reason.

    Twin copy: the canonical definition is in `hooks/shared/claude_md_manager.py`
    and this module cannot import from `hooks/shared/` (separate package), the
    same constraint that produced the `file_lock` and `_atomic_write_text`
    twins. The two bodies are gated identical by
    TestLineEndingHelperTwinCopyDrift.

    Args:
        name: The leaf name of the target, resolved against `parent_fd`.
        parent_fd: An open descriptor for the directory the write binds into.

    Returns:
        Either the two-character CRLF sequence or a single newline.
    """
    try:
        fd = os.open(name, os.O_RDONLY, dir_fd=parent_fd)
    except (OSError, NotImplementedError):
        return "\n"
    try:
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError:
        return "\n"
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    crlf_count = raw.count(b"\r\n")
    lf_count = raw.count(b"\n") - crlf_count
    return "\r\n" if crlf_count > lf_count else "\n"


def _restore_line_ending(content: str, line_ending: str) -> str:
    """
    Apply `line_ending` to `content`, whatever endings `content` arrives with.

    IT NORMALISES FIRST, AND IT IS NOT SAFE WITHOUT THAT. An earlier form
    recorded a PRECONDITION that content reaches it with no carriage return in
    it, and applied a plain replace. That held while one caller fed it. At this
    seam the callers are ten and the seam cannot see where their content came
    from, so the precondition is a claim about callers rather than a property of
    this function. A plain replace on a string that carries CRLF gives a doubled
    carriage return, which is corruption of the user's own file.

    SO CRLF GOES BACK TO LF FIRST, AND THEN THE ENDING GOES ON. A caller that
    restores for itself is then a no-op rather than a corruption, which is a
    defect this function makes harmless rather than one it hides. The LF branch
    keeps its early return, so an LF file is byte-identical to what this wrote
    before.

    Twin copy: the canonical definition is in `hooks/shared/claude_md_manager.py`
    and this module cannot import from `hooks/shared/` (separate package). The
    two bodies are gated identical by TestLineEndingHelperTwinCopyDrift.

    Args:
        content: Full file contents, with any line endings.
        line_ending: The ending to write, from `_detect_line_ending`.

    Returns:
        `content` with its endings replaced, or unchanged when the target is LF.
    """
    if line_ending == "\n":
        return content
    return content.replace("\r\n", "\n").replace("\n", line_ending)


def _atomic_write_text(target: Path, content: str, project_root: Path) -> None:
    """Replace `target`'s contents with `content` atomically, iff the directory
    the write will bind into is contained within `project_root` (#1247).

    `Path.write_text` truncates the file and THEN writes, so a crash, a full
    disk, or a kill between those two steps leaves a TRUNCATED CLAUDE.md. That
    file is gitignored and untracked in the projects this runs in, so there is
    no recovery path -- the user's pinned context is simply gone.

    Writing to a sibling temp file and renaming makes the replacement atomic: a
    reader sees either the whole old file or the whole new one, never a partial
    write. The temp file is created in the TARGET'S OWN DIRECTORY because
    `os.replace` is only atomic within a single filesystem.

    CONTAINMENT -- WHY THERE IS NO PATH RESOLVER HERE
    -------------------------------------------------

    PRECONDITION. This guard eliminates one class outright and narrows another.
    The class eliminated is disagreement between two path resolutions: only
    one traversal happens here and its result is held OPEN, so no second
    resolution exists to disagree with it. What is narrowed is time. The walk
    establishes ancestry AT THE INSTANT OF THE WALK, and a descriptor pins
    IDENTITY, not POSITION -- so containment holds provided the directory the
    write binds into does not change position relative to the anchor between
    the walk and the rename. Only the chain from that directory up to the
    anchor matters; relocating anything off it is irrelevant.

    An earlier form of this guard compared `str(target.resolve())` against the
    resolved root. `resolve()` follows every component INCLUDING the leaf; the
    write follows only the PARENT chain and then binds the leaf as a directory
    entry. Those are two independent traversals of two different path
    expressions, and on a two-leg symlink topology they name different
    directories -- so the guard certified a path the write never touched.

    The general defect is that `Path.resolve()` and `os.path.realpath` are
    SECOND implementations of path resolution, running in userspace, which the
    write does not use. A predicate built on one is sound exactly while the two
    agree, and the disagreement set (symlink loops, absent components) is
    discovered, never bounded. So this function asks the kernel instead:

      anchor  = (st_dev, st_ino) of os.stat(project_root)
      node    = the directory the write will bind into, held OPEN
      walk up via ".." comparing (st_dev, st_ino) until the anchor matches
      (CONTAINED) or a directory is its own parent (filesystem root, REFUSE)

    and then performs temp-create, fchmod, fsync, rename and cleanup THROUGH
    that same descriptor. The object CHECKED is the object MUTATED, by
    construction rather than by agreement. Consequences that fall out rather
    than being bolted on: version-invariant (no `Path.resolve()` exists here, so
    its 3.9-3.12 vs 3.13+ RuntimeError split is unreachable, not caught);
    strict (an absent parent raises instead of being lexically completed);
    immune to case-folding, Unicode normalisation form and trailing separators,
    because nothing is compared as text; and sibling-prefix (`/abc` under
    `/ab`) is refused structurally, since `/abc` never walks up to `/ab`'s
    inode.

    The parent is opened FOLLOWING symlinks -- see the inline note. Mounts
    beneath the project are ALLOWED: `..` from a mount root yields the mount
    POINT's parent, so the walk crosses one transparently, and the write still
    lands inside the anchor's subtree.

    THE LEAF IS NEVER CONSULTED, AND THAT COUPLES THIS TO THE WRITE SHAPE
    --------------------------------------------------------------------
    Containment is entirely a property of the parent chain, because the parent
    chain is the only part the kernel traverses on the way to the write. A leaf
    symlink pointing OUTSIDE the root is therefore ALLOWED, and that is the
    correct verdict, not a concession: `os.replace` is renameat(2), which
    unlinks whatever entry sits at the final name and binds the temp file's
    inode there. It never opens the leaf and never follows it, so the payload
    lands at the in-project entry and any outside victim is left byte-intact.

    That ALLOW is sound ONLY while the write replaces the leaf ENTRY rather
    than writing THROUGH it. Two rewrites would silently convert every such
    ALLOW into a real escape, with this predicate untouched: (1) resolving the
    target once and using it downstream -- proposed as a cheap way to make the
    check and the act agree, which it does, on the WRONG side, by making the
    write follow the leaf; (2) replacing temp-plus-rename with an open/truncate
    on the target. MEASURED, so the guarantee is stated at its real strength:
    with either rewrite spliced in, `TestR6InProjectRedirectResidualDocumented`
    turns RED on its victim-untouched assertion, so the in-project half of this
    coupling IS pinned by an executing test today. The out-of-project half is
    pinned separately, and could not be pinned at all before this predicate,
    because the earlier one refused that topology outright.

    Callers must already hold `file_lock` for the target. The lock closes the
    concurrent-writer window; this closes the crash/truncation window.

    Requires read+execute on the target's directory and write permission on it
    (to create the temp), where a bare `write_text` needed only permission on
    the file itself. A read-only directory holding a writable CLAUDE.md fails
    the write rather than truncating it -- a safe direction, but a real
    behaviour change.

    SCOPE LIMIT, stated because the natural summary of this change overclaims:
    `file_lock` runs BEFORE this function at every call site and does its own
    unprotected `target_file.resolve()`. Removing `Path.resolve()` from this
    guard makes the GUARD version-invariant; it does NOT make the write path
    version-invariant end-to-end, and a symlink loop still raises upstream.

    NOTE: a deliberate duplicate of `_atomic_write_text` in
    `hooks/shared/claude_md_manager.py`. This module cannot import from
    `hooks/shared/` (separate package), the same constraint that produced the
    `file_lock` twin above. This twin IS drift-gated by
    TestAtomicWriteTwinCopyDrift: the
    containment CHECK is a security invariant that must not silently diverge
    between the hook and skill copies (#1118-class hazard). That gate compares
    only THIS function's body, which is why the check is inlined here rather
    than extracted -- a named helper would have to be twinned too, and would
    sit outside every drift gate in the repo.

    Args:
        target: Path to replace. Its parent directory must already exist.
        content: Full file contents to write.
        project_root: The trusted base directory `target` must be contained in.

    Raises:
        ContainmentError: the write's parent directory is not the project root
            or a descendant of it; or the boundary could not be established at
            all. Fail-CLOSED in every case, with a distinct message per cause.
    """
    # A MISSING ANCHOR IS REFUSED AT THE CONTROL, not left to the callers.
    #
    # None is not reachable here today: both writers guard, and the resolver
    # returns a PAIRED (None, None). But both of those guards test the TARGET
    # path, not the anchor, so the containment guarantee currently rests on a
    # resolver invariant that neither writer states. A resolver branch returning
    # `(path, None)` would put None here.
    #
    # AND TODAY IT WOULD FAIL CLOSED BY ACCIDENT, WHICH IS THE REASON THIS LINE
    # EXISTS. `os.stat(str(None))` stats the literal relative path "None",
    # which raises -- until a directory named `None` exists in the working
    # directory, at which point that directory silently BECOMES the containment
    # anchor and every write is measured against it. A security control must not
    # depend on a filename not existing. Make the state unrepresentable here.
    if project_root is None:
        raise ContainmentError(
            "refusing write: no containment anchor was supplied"
        )

    # #1247 CONTAINMENT, fail-CLOSED, BEFORE anything is created: kernel object
    # ancestry on a pinned directory descriptor. No Path.resolve(), no
    # os.path.realpath, no string comparison takes part in this decision.
    try:
        anchor_stat = os.stat(str(project_root))
        anchor_key = (anchor_stat.st_dev, anchor_stat.st_ino)
        # FOLLOWS symlinks, deliberately: this is exactly how the kernel will
        # traverse the parent chain for the write. O_NOFOLLOW here would refuse
        # any symlinked final component of the parent path -- including a benign
        # in-project `.claude` -> `<project>/config/claude`, which the pre-#1247
        # code allowed -- a NEW over-block on an axis that is not containment.
        # It would also add nothing: the ancestry test below runs ON this
        # descriptor, so there is no check-then-open gap for it to close.
        parent_fd = os.open(str(target.parent), os.O_RDONLY | os.O_DIRECTORY)
    except (OSError, NotImplementedError):
        # An absent parent, a parent that is not a directory, a symlink loop
        # (ELOOP), and an unsupported-primitive failure all land here. Bare
        # RuntimeError is deliberately NOT caught: it is unreachable, because no
        # Path.resolve() call exists in this function, and catching it would
        # imply one still did and invite one back. NotImplementedError is named
        # explicitly -- it is a RuntimeError SUBCLASS, and it is Python's
        # documented signal for an unsupported dir_fd argument.
        raise ContainmentError(
            "refusing write: cannot establish the containment boundary"
        )

    walked = []
    try:
        # 1024 is an INLINE LITERAL rather than a module constant because a
        # constant would sit outside the region the twin drift gate compares
        # (only this function's body) and could diverge between the twins
        # silently. It is a LIVENESS backstop, not a policy ceiling: a POSIX
        # path is PATH_MAX-bounded and every component costs at least two bytes
        # including its separator, so no reachable path carries this many
        # components. Reaching it means the filesystem is misreporting "..",
        # not that the path is legitimately deep -- which is why exhaustion
        # raises its own message below instead of the escape one. Normal
        # operation terminates at the filesystem root and never arrives here.
        contained = False
        node = parent_fd
        for _ in range(1024):
            node_stat = os.fstat(node)
            if (node_stat.st_dev, node_stat.st_ino) == anchor_key:
                contained = True
                break
            try:
                up = os.open("..", os.O_RDONLY | os.O_DIRECTORY, dir_fd=node)
            except NotImplementedError:
                # NARROW BY DESIGN -- only NotImplementedError is mapped here.
                # A genuine OSError from this open (EACCES on an ancestor the
                # user cannot read) must keep propagating RAW through the outer
                # handler; relabelling it would report a permission failure as
                # a capability failure.
                # NotImplementedError has to be named explicitly because it is
                # a RuntimeError SUBCLASS, NOT an OSError one, while
                # ContainmentError subclasses OSError. So the callers'
                # `except ContainmentError` / `except OSError` arms are blind
                # to it: unmapped, it would escape as-is and CRASH the hook
                # instead of failing closed into the site's opaque skip status.
                # This is the same reason given at the parent-directory open;
                # it applies wherever a dir_fd argument is passed, and this is
                # the second such site.
                raise ContainmentError(
                    "refusing write: platform lacks directory-descriptor "
                    "ancestry traversal"
                )
            walked.append(up)
            up_stat = os.fstat(up)
            if (up_stat.st_dev, up_stat.st_ino) == (
                node_stat.st_dev,
                node_stat.st_ino,
            ):
                # A directory that is its own parent is the filesystem root:
                # the walk is over and the anchor was never reached.
                break
            node = up
        else:
            raise ContainmentError(
                "refusing write: containment walk did not terminate"
            )
        if not contained:
            raise ContainmentError(
                "refusing write: target escapes the project containment boundary"
            )
    except BaseException:
        os.close(parent_fd)
        raise
    finally:
        for extra in walked:
            os.close(extra)

    try:
        # THE SEAM KEEPS THE LINE ENDING OF THE TARGET, FOR EVERY CALLER.
        # A caller reads the file with universal-newline translation, changes a
        # region, and hands the whole document back, so a CRLF file would be
        # written as LF and the user sees a whole-file rewrite they did not
        # make. Repairing that at the call sites is what produced one defect for
        # each site, so the seam owns it and a new write site inherits it.
        #
        # THE DETECTION RUNS HERE FOR TWO REASONS, AND THE POSITION IS PART OF
        # THE GUARANTEE. It is AFTER the containment walk, so it never reads a
        # path the walk has not blessed, and it goes THROUGH `parent_fd`, so the
        # bytes it samples come from the same kernel object the walk approved. A
        # read by name here would reintroduce the race this descriptor design
        # exists to remove, exactly as a chmod by name would.
        content = _restore_line_ending(
            content, _detect_line_ending(target.name, parent_fd)
        )
        tmp_name = f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(
                tmp_name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
                dir_fd=parent_fd,
            )
        except NotImplementedError:
            raise ContainmentError(
                "refusing write: platform lacks directory-descriptor file creation"
            )
        try:
            # os.fdopen takes ownership of fd only on success; if it raises, the
            # raw fd would leak (the cleanup below unlinks the temp FILE but
            # cannot close a descriptor it never received a handle for).
            try:
                # newline="" so this handle performs NO line-ending translation.
                # With newline=None, Python rewrites each "\n" to os.linesep,
                # which is "\n" here and "\r\n" on Windows, so the restore above
                # would emit "\r\r\n" there.
                #
                # THIS PRIMITIVE CHOOSES THE LINE ENDING AND THE CALLER MUST
                # NOT. That inverts what this comment said before the restore
                # moved here, and the inversion is the point: one property, one
                # owner. A caller that restores for itself makes the
                # substitution run two times. `_restore_line_ending` normalises
                # first, so that mistake is a no-op rather than a doubled
                # carriage return, and it is a defect either way. A source-level
                # arm reports a second owner.
                handle = os.fdopen(fd, "w", encoding="utf-8", newline="")
            except BaseException:
                os.close(fd)
                raise
            with handle:
                handle.write(content)
                handle.flush()
                # fchmod on the OPEN HANDLE, never os.chmod by name: a chmod by
                # name after the close would reintroduce the name-based race
                # this descriptor design exists to remove. It is NOT guarding
                # against over-permissiveness -- umask can only CLEAR bits, so
                # os.open(..., 0o600) cannot yield anything more permissive than
                # 0o600. Its actual effect is the opposite: it RESTORES an
                # owner-write bit a restrictive umask removed (measured: with
                # the open mode alone, umask 0o277 leaves 0o400). The property
                # is DETERMINISM -- the mode belongs to this function rather
                # than to the caller's umask. It precedes the fsync so the mode
                # change is part of what that fsync flushes.
                os.fchmod(handle.fileno(), 0o600)
                # Without the fsync the rename can be persisted while the data
                # behind it is not, which reintroduces the empty-file failure
                # this function exists to prevent.
                os.fsync(handle.fileno())
            try:
                os.replace(
                    tmp_name,
                    target.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
            except NotImplementedError:
                raise ContainmentError(
                    "refusing write: platform lacks directory-descriptor rename"
                )
        except BaseException:
            # Remove the temp rather than leave it beside the user's CLAUDE.md.
            # BEST-EFFORT, not absolute: if the removal itself fails the temp
            # survives, because nothing downstream of here can remove it. That
            # is the deliberate trade below -- a stray file is preferable to
            # losing the reason the write was refused.
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except (OSError, NotImplementedError):
                # SWALLOWED, not mapped -- the one capability site handled this
                # way, and deliberately so. This cleanup runs while an exception
                # is already in flight; anything raised here REPLACES it, and
                # the bare `raise` below never runs. The caller would then see
                # a cleanup failure instead of the containment refusal that
                # actually stopped the write, so a leftover temp file would
                # outrank the reason the write was refused. The original
                # exception wins; best-effort cleanup stays best-effort.
                # NotImplementedError is named for the same reason as at the
                # dir_fd sites above: it subclasses RuntimeError, NOT OSError,
                # so a bare `except OSError` is blind to it.
                pass
            raise
    finally:
        os.close(parent_fd)


def extract_managed_region(content: str) -> Optional[Tuple[str, int]]:
    """
    Extract the PACT-managed region from CLAUDE.md content.

    ⚠️ THIS TWIN IS DELIBERATELY NOT BYTE-IDENTICAL, AND IS NOT DRIFT-GATED.
    Its siblings (`file_lock`, `_atomic_write_text`) are pinned byte-for-byte;
    this one cannot be, because two differences here are LOCAL CONVENTIONS
    rather than divergence:

      * `Optional[Tuple[str, int]]` here vs `tuple[str, int] | None` there
      * `_MANAGED_START_MARKER` here vs `MANAGED_START_MARKER` there
        (this module private-prefixes what that one exports)

    The executable logic is otherwise identical. Do NOT "fix" either side
    toward the other and do NOT add a byte-identity gate: it would go red on
    arrival, on choices someone made, and a gate that is red on arrival gets
    deleted rather than investigated. A NORMALISED gate — mapping the constant
    names and the annotation syntax before comparing — is the real remedy and
    is deliberately deferred rather than invented here.

    Twin of hooks/shared/claude_md_manager.extract_managed_region — kept
    local because skills/pact-memory/scripts/ cannot import from hooks/shared/.

    Returns (region_text, start_offset) where start_offset is the absolute
    position of the first character after MANAGED_START_MARKER. Returns None
    if either marker is missing.
    """
    start_idx = content.find(_MANAGED_START_MARKER)
    if start_idx == -1:
        return None
    region_start = start_idx + len(_MANAGED_START_MARKER)
    end_idx = content.find(_MANAGED_END_MARKER, region_start)
    if end_idx == -1:
        return None
    return content[region_start:end_idx], region_start


def _find_existing_claude_md(base: Path) -> Optional[Path]:
    """
    Return the first existing CLAUDE.md under `base`, checking both
    supported locations in priority order.

    Claude Code accepts project memory at either `.claude/CLAUDE.md` (new
    default) or `./CLAUDE.md` (legacy). This helper checks `.claude/CLAUDE.md`
    first, then falls back to `./CLAUDE.md`, returning the first match or
    None if neither exists.

    Args:
        base: Directory to probe for CLAUDE.md.

    Returns:
        Path to the existing CLAUDE.md, or None if neither location exists.
    """
    dot_claude = base / ".claude" / "CLAUDE.md"
    if dot_claude.exists():
        return dot_claude
    legacy = base / "CLAUDE.md"
    if legacy.exists():
        return legacy
    return None


def _get_claude_md_path() -> Optional[Path]:
    """
    Get the path to CLAUDE.md in the project root.

    Uses CLAUDE_PROJECT_DIR environment variable if set, then falls back
    to git worktree/repo root detection, then to current working directory.
    At each level, checks both `.claude/CLAUDE.md` (new default) and
    `./CLAUDE.md` (legacy) in priority order.

    Note: This mirrors the resolution strategy in hooks/staleness.py
    (get_project_claude_md_path). Kept as a local copy because this
    module lives in skills/ and cannot import from hooks/.

    Returns:
        Path to CLAUDE.md if it exists, None otherwise.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        found = _find_existing_claude_md(Path(project_dir))
        if found is not None:
            return found

    # Fallback: detect git root (worktree-safe)
    # Uses --git-common-dir instead of --show-toplevel because the latter
    # returns the worktree path when run inside a worktree, which may not
    # contain CLAUDE.md. --git-common-dir always points to the shared .git
    # directory; its parent is the main repo root where CLAUDE.md lives.
    # git returns this path relative to the invoking directory when run at a
    # repo root (the bare ".git") and absolute elsewhere, so resolve a relative
    # result against the cwd before taking its parent.
    # NOTE: Twin pattern in memory_api.py (_detect_project_id) and
    #       hooks/staleness.py (get_project_claude_md_path) -- keep in sync.
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
                return found
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Last resort: current working directory
    return _find_existing_claude_md(Path.cwd())


def _resolve_display_claude_md_with_base() -> Tuple[Optional[Path], Optional[Path]]:
    """
    Resolve the display CLAUDE.md AND the trusted base directory it was found
    under, so a write caller can containment-check the target against the base
    the resolver actually used (#1247).

    Same resolution order as `_resolve_display_claude_md_path` (which is now a
    thin wrapper returning `[0]`):
      1. CLAUDE_PROJECT_DIR env var, if set -> that dir's .claude/CLAUDE.md
         (preferred) or ./CLAUDE.md (legacy).
      2. Git worktree root via `git rev-parse --show-toplevel` -> the same
         .claude/-then-legacy probe under the worktree root.
      3. Main repo root via `git rev-parse --git-common-dir`.parent -> the
         same probe. Reached only when the worktree is NOT a session root
         (branch 2 found nothing): under the PACT `.worktrees/` convention no
         session is rooted in the worktree, so the file the session reads is
         the main repo's. Without this branch that write is lost (returns
         None); with it the write lands where the session reads.
      4. Current working directory -> the same probe.

    Branch 2 anchors the WORKTREE root (--show-toplevel) so a worktree that IS
    a session root updates its OWN display file; branch 3 falls back to
    _get_claude_md_path's MAIN-repo anchor (--git-common-dir) for the common
    case where it is not. Because branch 2 precedes branch 3, the two resolvers
    now differ ONLY in that worktree-root branch: in a non-worktree checkout
    both branches resolve the same directory, so the [0] of this result is
    identical to _get_claude_md_path's.

    The returned `base` is the branch's directory captured BEFORE descending
    into `.claude` (the arg passed to `_find_existing_claude_md`), NOT the
    returned path and NOT a re-derivation. That is the trusted pre-resolve
    anchor that makes the #1247 containment check non-vacuous: an F1
    symlinked-parent `.claude` perturbs the target's resolve() but not the
    base's, so containment catches the escape.

    This never CREATES a CLAUDE.md (the orchestrator manages the file's
    lifecycle); it only probes for an existing one.

    Returns:
        (path, base) where path is the existing display CLAUDE.md and base is
        the directory it was found under; (None, None) if none exists.
    """
    # Resolution must never raise into the sync path; on any failure (a bad
    # CLAUDE_PROJECT_DIR value, an inaccessible probe target, or a deleted cwd)
    # return (None, None) so the caller skips the sync and the save still succeeds.
    try:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if project_dir:
            base = Path(project_dir)
            found = _find_existing_claude_md(base)
            if found is not None:
                return found, base

        # Worktree root: --show-toplevel returns the worktree directory when run
        # inside a worktree (and the main repo root otherwise), matching the
        # directory session_init/session_resume target for the session's CLAUDE.md.
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                worktree_root = Path(result.stdout.strip())
                found = _find_existing_claude_md(worktree_root)
                if found is not None:
                    return found, worktree_root
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Main-repo root via --git-common-dir. Under the PACT `.worktrees/`
        # convention no session is ever rooted in the worktree, so branch 2
        # found nothing and the file the session actually reads is the MAIN
        # repo's. --git-common-dir points at the shared .git dir whether run
        # from the main repo or a linked worktree, so its parent is the main
        # repo root in both. This is _get_claude_md_path's exact anchor.
        #
        # The is_absolute() guard is load-bearing, not decoration: git returns
        # a RELATIVE path (".git", "../.git") when run at a repo root or subdir,
        # and _find_existing_claude_md does a bare `base / "CLAUDE.md"` with no
        # normalisation, so a relative base would yield a cwd-relative Path and
        # a cwd-relative lock sidecar (the exact divergence D2 just closed).
        # Reused verbatim from _get_claude_md_path.
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
    except Exception as e:
        logger.debug("display CLAUDE.md resolution failed, skipping sync: %s", e)
        return None, None


def _resolve_display_claude_md_path() -> Optional[Path]:
    """
    Resolve the CLAUDE.md the CURRENT SESSION displays (path only).

    Thin wrapper over `_resolve_display_claude_md_with_base` (added for #1247);
    read-only callers and the resolver-parity lint use this Path-only name,
    while the 2 write callers use the with-base variant to get the containment
    anchor. See that function for the full resolution order and the base
    semantics.

    Returns:
        Path to the existing display CLAUDE.md, or None if none exists.
    """
    return _resolve_display_claude_md_with_base()[0]


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count for a text string.

    Uses word count multiplied by 1.3 as a simple approximation for
    English text. No external tokenizer dependency required.

    NOTE: Twin copy exists in hooks/staleness.py (estimate_tokens) -- keep in sync.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count (integer).
    """
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def _compress_memory_entry(entry: str) -> str:
    """
    Compress a full memory entry to a date header, a summary and its key.

    Preserves the date header, extracts the first sentence from the Context
    field, and KEEPS THE `**Memory ID**` LINE. The other fields (Goal,
    Decisions, Lessons, Files) are dropped.

    THE POINTER IS KEPT BECAUSE THE ROUTE IS NOT THE KEY. The section
    comment tells a reader that the full history is searchable through the
    pact-memory skill, which is the ROUTE. The `**Memory ID**` line is the
    KEY. This function dropped the key and left the route, so recovery of a
    compressed entry fell back to a content search across at most 120
    characters of summary. One line of 47 characters restores the key, and
    the whole design accepts loss at this rendering ONLY because the loss is
    recoverable from the store.

    Args:
        entry: Full markdown memory entry string starting with ### YYYY-MM-DD.

    Returns:
        Compressed entry: date header, one-line summary, and the memory id
        where the entry carried one.
    """
    lines = entry.strip().split("\n")
    if not lines:
        return entry

    # Preserve the date header line (### YYYY-MM-DD HH:MM)
    date_line = lines[0]

    # Preserve the recovery key. An entry that carried no id keeps none,
    # because there was none to keep. That is not a regression, and the
    # worst-case cost below assumes the line IS present, so the derived
    # ceiling is conservative for the entries that lack it.
    id_line = ""
    for line in lines[1:]:
        if line.startswith("**Memory ID**"):
            id_line = line
            break

    # Find the Context field and extract its first sentence
    summary_text = ""
    for line in lines[1:]:
        if line.startswith("**Context**:"):
            context_value = line.split("**Context**:", 1)[1].strip()
            # Take first sentence (up to first ". " boundary, or first 120 chars).
            # Uses ". " instead of "." to avoid truncating at version numbers
            # like v2.3.1 or decimal values.
            period_idx = context_value.find(". ")
            if period_idx > 0 and period_idx < 120:
                summary_text = context_value[:period_idx + 1]
            else:
                summary_text = context_value[:120]
                if len(context_value) > 120:
                    summary_text += "..."
            break

    if not summary_text:
        # Fallback: use first non-header line content
        for line in lines[1:]:
            stripped = line.strip()
            if stripped and stripped.startswith("**") and "**:" in stripped:
                # Extract value from any bold field
                summary_text = stripped.split("**:", 1)[1].strip()[:120]
                if len(stripped.split("**:", 1)[1].strip()) > 120:
                    summary_text += "..."
                break

    # The id line is appended LAST, so the compressed entry keeps the same
    # "pointer at the end" shape as an uncompressed one, and
    # `_apply_entry_token_ceiling` exempts it by PREFIX at whatever index it
    # sits, so the two agree without either depending on a position.
    tail = f"\n{id_line}" if id_line else ""
    if summary_text:
        return f"{date_line}\n**Summary**: {summary_text}{tail}"
    return f"{date_line}{tail}"


def _apply_entry_token_ceiling(entry: str, ceiling: int) -> str:
    """
    Cut ONE entry to a token ceiling by dropping whole field LINES.

    A CHARACTER BOUND CANNOT ENFORCE A TOKEN BUDGET. The per-field bound in
    the two formatters is in CHARACTERS, the section budget is in TOKENS,
    and the producer of a field value controls the ratio through whitespace
    density. So the budget is enforced a second time, in its own unit, here.

    THE CUT DROPS WHOLE LINES FROM THE END. It never cuts inside a line: a
    mid-line cut can leave a partial ``**Field**: `` fragment, and a cut at
    a line break puts the remainder at the START of a line, which is the
    shape the whole sanitize exists to prevent.

    TWO LINES ARE EXEMPT AND ALWAYS SURVIVE:

    1. The ``### {date}`` header. Without it the entry stops parsing as an
       entry, and the date-led heading is what excludes it from the pin count.
    2. The ``**Memory ID**`` line. It is the pointer to the durable record.
       The whole design accepts truncation rather than refusal BECAUSE a
       loss at this rendering is recoverable from the store, and that
       argument holds only while the pointer survives the cut.

    THE MEMORY ID LINE IS THE LAST LINE OF AN ENTRY, so a drop-from-the-end
    that did not exempt it would remove the recovery pointer FIRST, quietly
    undoing the argument above while every test stayed green.

    Args:
        entry: One formatted markdown entry, starting with its date header.
        ceiling: Maximum estimated tokens for this entry alone.

    Returns:
        The entry, cut to whole lines, at or below the ceiling where the
        two exempt lines permit it.
    """
    if _estimate_tokens(entry) <= ceiling:
        return entry

    lines = entry.split("\n")
    if len(lines) <= 1:
        return entry

    # Index 0 is the date header. A `**Memory ID**` line is matched by
    # PREFIX wherever it sits, rather than by position, so the exemption
    # does not depend on it staying last.
    exempt = {0}
    for index, line in enumerate(lines):
        if line.startswith("**Memory ID**"):
            exempt.add(index)

    # DROP WHOLE LINES FIRST, from the end, and stop at ONE remaining
    # droppable line. That last line is handled below instead of dropped.
    kept = list(range(len(lines)))
    droppable = [i for i in reversed(range(len(lines))) if i not in exempt]
    for index in droppable[:-1] if droppable else []:
        if _estimate_tokens("\n".join(lines[i] for i in kept)) <= ceiling:
            break
        kept.remove(index)

    if _estimate_tokens("\n".join(lines[i] for i in kept)) <= ceiling:
        return "\n".join(lines[i] for i in kept)

    # LAST RESORT: TRUNCATE THE FINAL DROPPABLE LINE IN PLACE RATHER THAN
    # DROP IT, AND THE CAUSE IS A MEASURED PRODUCTION DEFECT.
    #
    # A save that carries a CONTEXT and nothing else is an ORDINARY save, and
    # it renders as TWO lines: the date header and one field line. The header
    # is exempt, so that field line is the only droppable one. A pure
    # whole-line rule removed it and left a DATED HEADING WITH NO CONTENT.
    # Where such a save carries no memory id, the entry then kept NO POINTER
    # TO THE STORE either, and the argument that makes this design prefer
    # truncation to refusal is that the loss at this rendering is RECOVERABLE
    # FROM THE STORE. At that shape the recovery pointer was gone too, so the
    # cut destroyed the property the whole design rests on.
    #
    # THIS DOES NOT REOPEN THE MID-LINE-CUT TRAP. That trap has two causes: a
    # cut can leave a partial `**Field**: ` fragment, and a cut at a line
    # break can put the remainder at the START of a line. A truncation that
    # KEEPS THE LINE PREFIX and appends "..." does neither, because it EMITS
    # NO NEWLINE, so it can open no line. The forbidden class is wider than
    # the cause that motivates it, and this is the part outside the cause.
    #
    # Uses the same `[:limit - 3] + "..."` convention as the field sanitize.
    last = droppable[-1]
    line = lines[last]
    fitted = list(kept)
    overhead = _estimate_tokens(
        "\n".join(lines[i] if i != last else "" for i in fitted)
    )
    budget_words = max(0, int((ceiling - overhead) / 1.3))

    # DEGENERATE EDGE: DROP THE LINE RATHER THAN EMIT A MANGLED LABEL.
    # The `**Field**: ` label is ONE word, and the ellipsis step cuts 3
    # characters off the END of what it keeps. At a word budget of 1 the
    # only kept word IS the label, so the cut lands INSIDE it and emits
    # `**Context...`. At a budget of 0 the line becomes a bare `...`.
    # BOTH ARE THE PARTIAL `**Field**: ` FRAGMENT that the cut rule exists
    # to prevent, so this edge would defeat the guard at its own boundary.
    # MEASURED by a ceiling sweep: the label survives whole at a budget of
    # 2 or more, because the cut then lands in a VALUE word.
    if budget_words < 2:
        fitted.remove(last)
        return "\n".join(lines[i] for i in fitted)

    words = line.split()
    truncated = " ".join(words[:budget_words])
    if len(truncated) < len(line):
        truncated = truncated[:max(0, len(truncated) - 3)] + "..."
    lines[last] = truncated
    return "\n".join(lines[i] for i in fitted)


def _apply_token_budget(
    entries: List[str],
    token_budget: int
) -> List[str]:
    """
    Apply a token budget to a list of memory entries.

    Strategy: Cut each entry to the per-entry ceiling. Then compress older
    entries to single-line summaries, and if the total is above budget,
    reduce the number of entries shown.

    THE NEWEST ENTRY IS NEVER COMPRESSED AND NEVER DROPPED. IT CAN BE
    BOUNDED. This docstring said "keep the newest entry in full", which
    conflated THREE properties: not compressed, not dropped, not modified.
    The ceiling does not compress and it does not drop. IT BOUNDS. So the
    first two properties survive and the third does not, and the third is
    the product change that came with the per-entry ceiling: an entry above
    the ceiling loses its last field lines in this rendering, and the store
    keeps the full record.

    THE PER-ENTRY CEILING IS A FIXED EXPRESSION OVER THE MODULE CONSTANTS,
    NOT A FUNCTION OF THE `token_budget` ARGUMENT. Deriving it from the
    argument looks safer and is not: at a SMALL argument the ceiling falls
    below the size of an ordinary entry, so the newest entry gets cut and
    this function stops keeping it in full, which is its stated contract.
    The ceiling exists to stop ONE entry exhausting the SECTION, and the
    section is what the constants describe.

    Args:
        entries: List of memory entry strings (newest first).
        token_budget: Maximum estimated tokens for all entries combined.

    Returns:
        List of entries (some possibly cut or compressed) fitting within budget.
    """
    if not entries:
        return entries

    # Reserve room for the neighbours this function COMPRESSES rather than
    # drops, then give the rest of the section budget to the newest entry.
    # The newest entry is never compressed and the drop loop is
    # `while len(result) > 1`, so without this ceiling one dense entry can
    # exhaust the section on its own and evict every genuine neighbour.
    entry_ceiling = (
        WORKING_MEMORY_TOKEN_BUDGET
        - (MAX_WORKING_MEMORIES - 1) * COMPRESSED_ENTRY_TOKEN_CEILING
    )
    entries = [_apply_entry_token_ceiling(e, entry_ceiling) for e in entries]

    # Check if already within budget
    total_tokens = sum(_estimate_tokens(e) for e in entries)
    if total_tokens <= token_budget:
        return entries

    # Strategy: keep newest entry full, compress the rest
    result = [entries[0]]
    for entry in entries[1:]:
        compressed = _compress_memory_entry(entry)
        result.append(compressed)

    # Check if compressed version fits
    total_tokens = sum(_estimate_tokens(e) for e in result)
    if total_tokens <= token_budget:
        return result

    # Still over budget: drop entries from the end until we fit.
    # Subtract the popped entry's tokens instead of recalculating the full sum.
    while len(result) > 1 and total_tokens > token_budget:
        removed = result.pop()
        total_tokens -= _estimate_tokens(removed)

    return result


def _sanitize_prompt_field(
    value: str,
    limit: int = _REFRESH_FIELD_TRUNCATION_LIMIT,
) -> str:
    """Sanitize a record field value for interpolation into CLAUDE.md.

    Twin of hooks/shared/session_resume._sanitize_prompt_field — kept local
    because skills/pact-memory/scripts/ cannot import from hooks/shared/.
    Body MUST stay byte-identical to the canonical copy (drift test enforces
    this); this docstring is allowed to differ. Change either copy and you
    change both in the SAME commit.

    Collapses control characters to single spaces, strips, and bounds the
    length. Callers MUST sanitize BEFORE they test the value for
    truthiness: an internal failure returns ``""`` so the caller drops that
    field's LINE, and a test of the RAW value would emit the field label
    with an empty value instead.
    """
    try:
        cleaned = _PROMPT_CONTROL_CHARS_RE.sub(" ", value).strip()
        if len(cleaned) > limit:
            cleaned = cleaned[:limit - 3] + "..."
        return cleaned
    except Exception:
        return ""


def _format_memory_entry(
    memory: Dict[str, Any],
    files: Optional[List[str]] = None,
    memory_id: Optional[str] = None
) -> str:
    """
    Format a memory as a markdown entry for CLAUDE.md.

    Args:
        memory: Memory dictionary with context, goal, decisions, etc.
        files: Optional list of file paths associated with this memory.
        memory_id: Optional memory ID to include for database reference.

    Returns:
        Formatted markdown string for the memory entry.
    """
    # Get date and time for header
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M")

    lines = [f"### {date_str}"]

    # EVERY field value below is SANITIZED BEFORE IT IS TESTED FOR
    # TRUTHINESS, and the order is load-bearing. `_sanitize_prompt_field`
    # returns "" on an internal failure so the caller drops that field's
    # LINE; a test of the RAW value would pass, and then emit a bare
    # "**Context**: " with no value after it. Sanitize, test the SANITIZED
    # value, then append.

    # Add context if present
    context = _sanitize_prompt_field(str(memory.get("context") or ""))
    if context:
        lines.append(f"**Context**: {context}")

    # Add goal if present
    goal = _sanitize_prompt_field(str(memory.get("goal") or ""))
    if goal:
        lines.append(f"**Goal**: {goal}")

    # Add decisions if present
    decisions = memory.get("decisions")
    if decisions:
        if isinstance(decisions, list):
            # Extract decision text from list of dicts or strings
            decision_texts = []
            for d in decisions:
                if isinstance(d, dict):
                    decision_texts.append(d.get("decision", str(d)))
                else:
                    decision_texts.append(str(d))
            # Sanitize the JOINED value, not each item: the join is what
            # reaches the file, and a per-item bound would let N items
            # multiply past the line bound the sanitize exists to set.
            joined = _sanitize_prompt_field(", ".join(str(t) for t in decision_texts))
            if joined:
                lines.append(f"**Decisions**: {joined}")
        elif isinstance(decisions, str):
            cleaned = _sanitize_prompt_field(decisions)
            if cleaned:
                lines.append(f"**Decisions**: {cleaned}")

    # Add lessons if present
    lessons = memory.get("lessons_learned")
    if lessons:
        if isinstance(lessons, list) and lessons:
            joined = _sanitize_prompt_field(", ".join(str(l) for l in lessons))
            if joined:
                lines.append(f"**Lessons**: {joined}")
        elif isinstance(lessons, str):
            cleaned = _sanitize_prompt_field(lessons)
            if cleaned:
                lines.append(f"**Lessons**: {cleaned}")

    # Add reasoning chains if present
    reasoning = memory.get("reasoning_chains")
    if reasoning:
        if isinstance(reasoning, list) and reasoning:
            joined = _sanitize_prompt_field(", ".join(str(r) for r in reasoning))
            if joined:
                lines.append(f"**Reasoning chains**: {joined}")
        elif isinstance(reasoning, str):
            cleaned = _sanitize_prompt_field(reasoning)
            if cleaned:
                lines.append(f"**Reasoning chains**: {cleaned}")

    # Add agreements if present
    agreements = memory.get("agreements_reached")
    if agreements:
        if isinstance(agreements, list) and agreements:
            joined = _sanitize_prompt_field(", ".join(str(a) for a in agreements))
            if joined:
                lines.append(f"**Agreements**: {joined}")
        elif isinstance(agreements, str):
            cleaned = _sanitize_prompt_field(agreements)
            if cleaned:
                lines.append(f"**Agreements**: {cleaned}")

    # Add disagreements resolved if present
    disagreements = memory.get("disagreements_resolved")
    if disagreements:
        if isinstance(disagreements, list) and disagreements:
            joined = _sanitize_prompt_field(", ".join(str(d) for d in disagreements))
            if joined:
                lines.append(f"**Disagreements resolved**: {joined}")
        elif isinstance(disagreements, str):
            cleaned = _sanitize_prompt_field(disagreements)
            if cleaned:
                lines.append(f"**Disagreements resolved**: {cleaned}")

    # Add files if present
    if files:
        # A path field, so the wider bound: legitimate absolute paths are long.
        joined_files = _sanitize_prompt_field(
            ", ".join(str(f) for f in files), _REFRESH_PATH_TRUNCATION_LIMIT
        )
        if joined_files:
            lines.append(f"**Files**: {joined_files}")

    # Add memory ID if provided
    if memory_id:
        # AN IDENTIFIER, NOT FREE TEXT. The free-text bound of 200 is 3
        # times what the generator emits, and the store does not bound this
        # value at its ingress, so a caller-supplied id took the widest
        # bound in the classification.
        cleaned_id = _sanitize_prompt_field(
            str(memory_id), _REFRESH_IDENTIFIER_TRUNCATION_LIMIT
        )
        if cleaned_id:
            lines.append(f"**Memory ID**: {cleaned_id}")

    return "\n".join(lines)


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


def _parse_working_memory_section(
    content: str
) -> Tuple[str, str, str, List[str]]:
    """
    Parse CLAUDE.md content to extract working memory section.

    Round 10 structural guarantee: the parser searches within the
    PACT-managed region only. This region contains only plugin-generated
    content (no user-authored fenced code blocks), so fence-aware scanning
    is unnecessary. If the managed region is not present (pre-migration
    file), falls back to scanning the full content. Returned slices
    (before_section, after_section) are always from the FULL content for
    correct write-back.

    Args:
        content: Full CLAUDE.md file content.

    Returns:
        Tuple of (before_section, section_header_with_comment, after_section, existing_entries)
        where existing_entries is a list of individual memory entry strings.
    """
    # Bound to managed region if available (round 10).
    region_result = extract_managed_region(content)
    if region_result is not None:
        scan_text, offset = region_result
    else:
        scan_text, offset = content, 0

    # Pattern to find the Working Memory section.
    # Negative lookahead excludes the three plugin-managed boundary prefixes
    # from being consumed as the auto-managed comment — otherwise an empty
    # Working Memory section followed immediately by <!-- PACT_MEMORY_END -->
    # would greedily swallow the marker (#404).
    section_pattern = re.compile(
        r'^(## Working Memory)\s*\n'
        rf'(<!-- (?!(?:{_PACT_BOUNDARY_ALT}))[^>]*-->)?\s*\n?',
        re.MULTILINE
    )

    match = section_pattern.search(scan_text)

    if not match:
        # Section doesn't exist
        return content, "", "", []

    section_start = match.start() + offset
    section_header_end = match.end()

    # Find where the next ## section starts (end of working memory section).
    # No fence-awareness needed — managed region contains only plugin-generated
    # content (round 10 structural guarantee).
    next_section_pattern = re.compile(
        rf'(#\s|##\s(?!Working Memory)|---|<!-- (?:{_PACT_BOUNDARY_ALT}))',
    )
    section_end_rel = _find_terminator_offset(
        scan_text, section_header_end, next_section_pattern
    )
    section_end = section_end_rel + offset

    before_section = content[:section_start]
    section_content = scan_text[section_header_end:section_end_rel].strip()
    after_section = content[section_end:]

    # Parse existing entries (each starts with ### YYYY-MM-DD)
    entry_pattern = re.compile(r'^### \d{4}-\d{2}-\d{2}', re.MULTILINE)
    entry_starts = [m.start() for m in entry_pattern.finditer(section_content)]

    existing_entries = []
    for i, start in enumerate(entry_starts):
        if i + 1 < len(entry_starts):
            entry = section_content[start:entry_starts[i + 1]].strip()
        else:
            entry = section_content[start:].strip()
        existing_entries.append(entry)

    return before_section, WORKING_MEMORY_HEADER, after_section, existing_entries


def _project_root_of(claude_md_path: Path) -> Path:
    """
    Return the project directory that owns `claude_md_path`.

    CLAUDE.md lives at either `<project>/.claude/CLAUDE.md` (preferred) or
    `<project>/CLAUDE.md` (legacy), so the root is one or two levels up
    depending on which form the caller resolved.

    Used only for an EXPLICIT target, to produce the same containment anchor
    that `_resolve_display_claude_md_with_base` returns for a resolved one —
    the directory captured before descending into `.claude`, never a
    re-derivation from the leaf.

    The two-layout knowledge is owned by `hooks/shared/claude_md_manager.py`
    (`_DOT_CLAUDE_RELATIVE` / `_LEGACY_RELATIVE`); this module cannot import
    from that package and vendors twins throughout, so this mirrors it. If a
    THIRD location is ever supported, this must be swept with the others.
    """
    parent = claude_md_path.parent
    return parent.parent if parent.name == ".claude" else parent


class SyncResult:
    """Outcome of a working-memory sync: DID IT WRITE, and WHY NOT.

    `__bool__` is `wrote`, so every existing read of the result keeps its exact
    present meaning. `.reason` carries the discrimination that a bare bool
    could not: a refusal, a suppression and an unresolved target were all
    `False`, and arm 3 of the archival suppression suite proved that a refused
    sync and a suppressed one leave identical evidence on disk.

    THIS DELIBERATELY DOES NOT FOLLOW `_store_embedding`'s CONVENTION, AND THE
    POLARITY IS THE REASON. That function treats `None` as success and a string
    as a problem. THIS function treats `True` as success. The two conventions
    are inverted, so they cannot be shared: adopting the sibling's convention
    here would make a truthiness read report success on a refusal.

    THE ARGUMENT IS THE PRESERVED MEANING, NOT A COUNT OF CALL SITES.
    `__bool__ == wrote` returns exactly what a bare bool returned, so NO
    TRUTHINESS READER changes behaviour -- neither the truthiness readers that
    exist now, nor one written later by an author who never reads this class.
    Do not restate that argument as a tally of reads in the suite. A tally rots
    the next time a test lands, and it invites a future editor to re-derive the
    decision from a population instead of from the property. State the property.

    THE PROPERTY IS ABOUT TRUTHINESS READERS AND NOT ABOUT ALL CALLERS, AND
    THAT WIDTH IS THE CORRECTION RATHER THAN A QUALIFICATION. This paragraph
    said "no caller changes behaviour" and that was too wide: `__bool__`
    cannot rescue an IDENTITY comparison. For an instance of this class,
    `bool(s)` is True while `s is True` and `s == True` are both False, so
    `assert x is True` breaks where `assert x` does not. Seven assertions in
    the suite were identity comparisons and each one had to change. A reader
    who takes the wider claim will predict no breakage and be incorrect.

    Do not "fix" the inconsistency with `_store_embedding`; it is load-bearing.
    """

    __slots__ = ("wrote", "reason")

    # Reasons. WROTE is the only one for which `bool()` is True.
    WROTE = "wrote"
    REFUSED = "refused"          # guard declined; raised, then caught upstream
    SUPPRESSED = "suppressed"    # caller passed sync_to_claude=False
    UNRESOLVED = "unresolved"    # no CLAUDE.md resolved
    MISSING = "missing"          # resolved a path that does not exist
    FAILED = "failed"            # the write itself raised
    EMPTY = "empty"              # nothing to write; caller passed no entries

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.wrote = reason == self.WROTE

    def __bool__(self) -> bool:
        return self.wrote

    def __repr__(self) -> str:
        return f"SyncResult({self.reason!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, SyncResult):
            return self.reason == other.reason
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.reason)


class AmbientSyncRefused(RuntimeError):
    """Raised when a test process would sync to an ambiently-resolved CLAUDE.md."""


def _refuse_ambient_target_under_pytest(
    target: Optional[Path],
    claude_md_root: Optional[Path] = None,
) -> None:
    """Refuse an AMBIENT working-memory sync when a TEST PROCESS spawned us.

    THE GAP THIS CLOSES, AND WHY A FLAG WAS NOT ENOUGH. Three paths reach live
    operator state from a test: the database, refused by
    `cli._refuse_live_db_under_pytest`; the session marker, refused by the
    `PYTEST_CURRENT_TEST` check in `pact_session`; and this one, which had no
    refusal at all. Two of three failed closed and the third always wrote.

    `--no-sync` exists and works, but it is a CONVENTION -- it must be
    remembered at every call site. It was forgotten twice in one evening by the
    two people most alert to this exact hazard, so roughly twenty probe saves
    reached the operator's real file. A refusal keyed on the condition needs
    nobody to remember anything.

    AND A SANDBOXED HOME NEVER COVERED IT, which is why it went unnoticed: the
    target is not under HOME. It is resolved from CLAUDE_PROJECT_DIR, then two
    git anchors, then the working directory -- and that resolver is TOTAL, so
    there is no configuration in which it declines to pick a file.

    SCOPE, mirroring `_refuse_live_db_under_pytest` deliberately rather than
    inventing a second shape:
    - An EXPLICIT `target` is always allowed. A caller that names its file has
      said which file it means, and tests legitimately sync to a tmp path.
    - A DECLARED `claude_md_root` is always allowed, AND IT IS A STRONGER
      WARRANT THAN `target` RATHER THAN A SECOND LOOSENING. `target` is blind
      trust: the caller names a file and it is written. An anchor is CHECKED --
      the write must land inside it or `_atomic_write_text` refuses -- so a
      caller that declares a sandbox cannot escape it even by resolving to
      somebody else's file. That is what makes exempting the refusal sound for
      a test process instead of merely convenient.
    - An IN-PROCESS caller (`pytest` already imported) is out of scope, because
      the suite's own working-memory tests call this ambiently on purpose.
    - The same bounded gap applies: pytest pops `PYTEST_CURRENT_TEST` between
      items, so a spawn during collection or session-fixture setup is NOT
      covered.

    Raises AmbientSyncRefused rather than returning False, because save()
    already treats a sync failure as non-critical and logs it -- a quiet False
    would leave the refusal invisible, which is the failure mode being fixed.
    """
    if target is not None:
        return
    if claude_md_root is not None:
        return
    if "pytest" in sys.modules:
        return
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return
    raise AmbientSyncRefused(
        "refusing to sync working memory to an ambiently-resolved CLAUDE.md: "
        "PYTEST_CURRENT_TEST is set in this process's environment, so the "
        "destination would be the operator's live file. Pass an explicit "
        "target=, or use the CLI's --no-sync flag."
    )


def sync_to_claude_md(
    memory: Dict[str, Any],
    files: Optional[List[str]] = None,
    memory_id: Optional[str] = None,
    target: Optional[Path] = None,
    claude_md_root: Optional[Path] = None
) -> "SyncResult":
    """
    Sync a memory entry to the Working Memory section of CLAUDE.md.

    Maintains a rolling window of AT MOST MAX_WORKING_MEMORIES entries. New
    entries are added at the top of the section, and older ones are removed.

    THE COUNT IS A CAP, NOT A PROMISE, and this docstring said "the last 3"
    until the claim was measured. `_apply_token_budget` keeps the newest entry
    IN FULL and its drop loop is `while len(result) > 1`, so when that entry
    ALONE exceeded the whole-section budget the older ones were dropped and the
    section showed ONE.

    THAT REGIME IS CLOSED AND THE CAP IS STILL A CAP. `_apply_entry_token_ceiling`
    now bounds each entry below the section budget, so the newest entry cannot
    exhaust the section by itself and the older ones survive at their compressed
    size. The count remains a cap rather than a promise for the ordinary reason:
    the store can hold fewer entries than MAX_WORKING_MEMORIES.

    ITS SIBLING `sync_retrieved_to_claude_md` HOLDS THE SAME CAP BY A DIFFERENT
    MECHANISM, AND THE EARLIER DESCRIPTION OF THAT MECHANISM HERE WAS INCORRECT
    IN TWO PLACES. It said `_format_retrieved_entry` truncates each ENTRY to 200
    chars; it bounded the CONTEXT FIELD only, and the query, the goal and the
    memory id carried no bound at all. It then said the sibling's drop loop
    "never runs"; that loop was DRIVEN, reaching 547 tokens against its budget
    of 500 and evicting one genuine neighbour.

    WHAT IS CORRECT NOW, WITH ITS CONDITION. Each field of both formatters is
    bounded, and each entry of both sections is bounded in TOKENS. The sibling's
    drop loop CAN still run: three retrieved entries at the full character bound
    cost more than its budget, so an entry at the ceiling loses lines and a
    third entry can be dropped. A realistic retrieved entry sits far below the
    ceiling, because a query and a memory id are short. The two functions differ
    in POLICY and not in whether they bound: this one compresses its older
    entries before it drops any, and the sibling drops without compressing.

    This function is designed for graceful degradation - if CLAUDE.md doesn't
    exist or the sync fails for any reason, it logs a warning but doesn't
    raise an exception.

    THE TARGET IS CALLER-SPECIFIABLE. Without `target` the destination is
    resolved AMBIENTLY — from CLAUDE_PROJECT_DIR, then two git anchors, then
    the working directory — and a caller who knows which file it means has no
    way to say so. That is the root defect: not that the resolver is wrong,
    but that there is no override, so a caller's knowledge cannot reach the
    write. `target` is that override.

    AN ABSENT DESTINATION IS A SKIP — on EITHER branch, explicit or ambient.
    The guard below the branch join states it rather than leaving it to be
    inferred. This matters because the obvious resolver to compute a target
    with — `claude_md_manager.resolve_project_claude_md_path` — is TOTAL: on a
    miss it returns a `"new_default"` path rather than None. That is correct
    for a caller whose job is to create the file, and wrong here, where the
    orchestrator owns the file's lifecycle.

    The guard covered only the explicit branch when it was first written, on
    the reasoning that the ambient resolver returns None when it finds nothing
    so that skip rode along free. That is true, but it is a property of the
    RESOLVER rather than of this function — and a TOTAL resolver never returns
    None, so the arrangement failed in exactly the case it was supposed to
    cover. Below the join it depends on nobody else's promise.

    MEASURED, because the stronger version of this warning is not true today
    and repeating it would misdescribe the code: handed a path to a file that
    does not exist, this function does NOT create it. The read precedes the
    write, so the read raises and the degradation handler below returns False.
    What it does do is take the sidecar lock first — leaving a `.CLAUDE.md.lock`
    artifact in a directory it should never have touched — and report a warning
    that reads like a real failure rather than a skip.

    So the protection against creating is currently an ACCIDENT OF ORDERING,
    not a contract: it holds only while the write path happens to read first.
    A future change that tolerates a missing file — or writes before reading —
    turns it into a create, and nothing would fail. The guard converts that
    accident into a stated contract, which is the whole point of putting it
    here rather than trusting the resolver to encode it.

    So: compute the target AT THE CALLER, pass it here, and let the existence
    check below decide.

    Args:
        memory: Memory dictionary with context, goal, decisions, lessons_learned, etc.
        files: Optional list of file paths associated with this memory.
        memory_id: Optional memory ID to include for database reference.
        target: Explicit CLAUDE.md path to write. When omitted, the display
            CLAUDE.md is resolved ambiently exactly as before, so existing
            callers are unaffected. When given, it is used verbatim and is
            never created if absent.
        claude_md_root: Declared containment anchor. The write must land inside
            it or the containment check refuses. It does NOT steer resolution:
            the target is still found the same way, and a target that resolves
            outside the declared root is REFUSED rather than redirected. Omit it
            for today's behaviour, where the anchor comes from the resolution.
            Supplying it also exempts the ambient-sync refusal, because a
            checked boundary is a stronger warrant than the unchecked `target`.

    Returns:
        A `SyncResult`. It is TRUTHY exactly when the write happened, so a
        caller that only asks "did it write" reads it unchanged. `.reason`
        names the outcome in EVERY case, the successful one included, so a
        caller that must tell a refusal from a suppression now can.

        A REFUSAL DOES NOT COME BACK THIS WAY. The ambient-target guard RAISES
        `AmbientSyncRefused` before any of these returns, so `SyncResult.REFUSED`
        is produced by whoever catches it, not here. See the guard's own
        docstring for why it raises rather than returns.
    """
    _refuse_ambient_target_under_pytest(target, claude_md_root)

    if target is not None:
        claude_md_path = Path(target)
        resolved_root = _project_root_of(claude_md_path)
    else:
        claude_md_path, resolved_root = _resolve_display_claude_md_with_base()

    # THE DECLARED ANCHOR REPLACES THE CONTAINMENT BASE. IT DOES NOT STEER
    # RESOLUTION -- the target above is found exactly as it was before.
    # Narrowing the two Nones HERE is the point: `claude_md_root is None` means
    # "the caller declared nothing, behave as before", while `resolved_root is
    # None` means "resolution found nothing at all". Those are different facts,
    # so they are carried in different variables and only one decision reads
    # both. A `claude_md_root or resolved_root` would merge them and silently
    # treat a declared-nothing as a found-nothing.
    #
    # It is a PARAMETER and never a lookup: no line here derives an anchor. An
    # anchor computed from the same resolution the target came from would agree
    # with it by construction, which is precisely the independence the caller is
    # trying to buy.
    project_root = (
        Path(claude_md_root) if claude_md_root is not None else resolved_root
    )

    # BOTH HALVES, BECAUSE THE PAIRING IS THE RESOLVER'S PROMISE AND NOT THIS
    # FUNCTION'S. `_resolve_display_claude_md_with_base` returns either two
    # paths or two Nones -- every one of its five exits is guarded by an
    # `if found is not None` -- so today `project_root` cannot be None once
    # `claude_md_path` is not. MEASURED, and it is the ONLY reason the anchor
    # below is safe.
    #
    # That is exactly the arrangement the existence guard further down was moved
    # for: a caller depending on a property of a resolver it does not own. A
    # later branch returning `(found, None)` would slip a None past a check that
    # only asks about the path, and `_atomic_write_text` would stat the literal
    # relative path "None" as its containment anchor -- which raises today, but
    # silently anchors on a directory named `None` if one ever exists. Naming
    # both halves here costs one condition and depends on nobody's promise.
    if claude_md_path is None or project_root is None:
        logger.debug("CLAUDE.md not found, skipping working memory sync")
        return SyncResult(SyncResult.UNRESOLVED)

    # EXISTENCE GUARD, BELOW THE JOIN SO IT COVERS BOTH BRANCHES.
    #
    # It used to sit inside the explicit-target branch, on the reasoning that
    # an ambient resolve returns None when it finds nothing so that skip rides
    # along for free. That reasoning is TRUE, and it is a property of
    # `_resolve_display_claude_md_with_base` -- NOT of this function. The
    # comment then claimed the contract therefore held for both paths, which
    # did not follow: a TOTAL resolver never returns None, so the `is None`
    # check above would not fire and nothing else stood between it and the
    # write. The claim was exactly inverted against the hazard it named.
    #
    # Down here the guard depends on no other function's promise.
    #
    # THE TWO WAYS TO ARRIVE ARE DIFFERENT IN KIND, so they are reported
    # differently rather than collapsed into one message:
    #
    #   explicit + absent -- ORDINARY. A caller named a project whose CLAUDE.md
    #     does not exist yet. Expected, benign, fires in normal use: debug.
    #
    #   ambient + absent -- SHOULD NOT HAPPEN. The resolver is documented to
    #     return only existing paths, and a resolver that finds nothing returns
    #     None, which the check above already absorbed. So this arm is
    #     unreachable on the normal path, and an unreachable arm that fires is
    #     signal rather than noise: warning.
    #
    # A single undifferentiated check would make a resolver that quietly went
    # total indistinguishable from an ordinary skip, at debug level -- the same
    # two-unrelated-causes-on-one-check problem that costs you the control.
    #
    # THE WARNING NAMES BOTH CAUSES AND ASSERTS NEITHER. A file removed between
    # resolution and this line produces an identical observation and is not a
    # defect at all; the two are indistinguishable here. The level says "look
    # at this", the text must not say "this is a bug."
    #
    # NEITHER ARM CREATES. That is the contract: an absent target is a skip.
    if not claude_md_path.exists():
        if target is not None:
            logger.debug(
                "explicit sync target %s does not exist, skipping working "
                "memory sync (this never creates CLAUDE.md)", claude_md_path
            )
        else:
            logger.warning(
                "resolved display CLAUDE.md %s does not exist, skipping "
                "working memory sync (this never creates CLAUDE.md). Either "
                "the display resolver stopped returning only existing paths, "
                "or the file was removed after it resolved.", claude_md_path
            )
        return SyncResult(SyncResult.MISSING)

    try:
        # Serialize the FULL read-modify-write window under the shared sidecar
        # lock (see the "why lock the whole window" note above file_lock for the
        # read-under-lock / lock-identity / CLAUDE_PROJECT_DIR rationale).
        with file_lock(claude_md_path):
            # Read current content
            content = claude_md_path.read_text(encoding="utf-8")

            # Parse existing working memory section
            before_section, section_header, after_section, existing_entries = \
                _parse_working_memory_section(content)

            # Format new memory entry
            new_entry = _format_memory_entry(memory, files, memory_id)

            # Build new entries list: new entry first, then existing (up to max - 1)
            all_entries = [new_entry] + existing_entries
            trimmed_entries = all_entries[:MAX_WORKING_MEMORIES]

            # Apply token budget: compress older entries if over budget
            trimmed_entries = _apply_token_budget(
                trimmed_entries, WORKING_MEMORY_TOKEN_BUDGET
            )

            # Build new section content
            section_lines = [
                WORKING_MEMORY_HEADER,
                WORKING_MEMORY_COMMENT,
                ""  # Blank line after comment
            ]
            for entry in trimmed_entries:
                section_lines.append(entry)
                section_lines.append("")  # Blank line between entries

            section_text = "\n".join(section_lines)

            # Reconstruct file content
            if section_header:
                # Section existed, replace it
                new_content = before_section + section_text + after_section
            else:
                # Section didn't exist, append at end
                if not content.endswith("\n"):
                    content += "\n"
                new_content = content + "\n" + section_text

            # Write back to file (atomic: temp + rename, so a crash mid-write
            # cannot leave the always-loaded CLAUDE.md truncated)
            _atomic_write_text(claude_md_path, new_content, project_root)

        logger.info("Synced memory to CLAUDE.md Working Memory section")
        return SyncResult(SyncResult.WROTE)

    except Exception as e:
        logger.warning(f"Failed to sync memory to CLAUDE.md: {e}")
        return SyncResult(SyncResult.FAILED)


def _parse_retrieved_context_section(
    content: str
) -> Tuple[str, str, str, List[str]]:
    """
    Parse CLAUDE.md content to extract retrieved context section.

    Round 10 structural guarantee: same managed-region bounding as
    _parse_working_memory_section — see that function's docstring.

    Args:
        content: Full CLAUDE.md file content.

    Returns:
        Tuple of (before_section, section_header, after_section, existing_entries)
        where existing_entries is a list of individual memory entry strings.
    """
    # Bound to managed region if available (round 10).
    region_result = extract_managed_region(content)
    if region_result is not None:
        scan_text, offset = region_result
    else:
        scan_text, offset = content, 0

    # Pattern to find the Retrieved Context section.
    # Negative lookahead narrows to the plugin-managed boundary prefixes
    # — see _parse_working_memory_section for the full rationale (#404).
    section_pattern = re.compile(
        r'^(## Retrieved Context)\s*\n'
        rf'(<!-- (?!(?:{_PACT_BOUNDARY_ALT}))[^>]*-->)?\s*\n?',
        re.MULTILINE
    )

    match = section_pattern.search(scan_text)

    if not match:
        # Section doesn't exist
        return content, "", "", []

    section_start = match.start() + offset
    section_header_end = match.end()

    # Find where the next ## section starts (end of retrieved context section).
    # No fence-awareness needed — managed region contains only plugin-generated
    # content (round 10 structural guarantee).
    next_section_pattern = re.compile(
        rf'(#\s|##\s(?!Retrieved Context)|---|<!-- (?:{_PACT_BOUNDARY_ALT}))',
    )
    section_end_rel = _find_terminator_offset(
        scan_text, section_header_end, next_section_pattern
    )
    section_end = section_end_rel + offset

    before_section = content[:section_start]
    section_content = scan_text[section_header_end:section_end_rel].strip()
    after_section = content[section_end:]

    # Parse existing entries (each starts with ### YYYY-MM-DD)
    entry_pattern = re.compile(r'^### \d{4}-\d{2}-\d{2}', re.MULTILINE)
    entry_starts = [m.start() for m in entry_pattern.finditer(section_content)]

    existing_entries = []
    for i, start in enumerate(entry_starts):
        if i + 1 < len(entry_starts):
            entry = section_content[start:entry_starts[i + 1]].strip()
        else:
            entry = section_content[start:].strip()
        existing_entries.append(entry)

    return before_section, RETRIEVED_CONTEXT_HEADER, after_section, existing_entries


def _format_retrieved_entry(
    memory: Dict[str, Any],
    query: str,
    score: Optional[float] = None,
    memory_id: Optional[str] = None
) -> str:
    """
    Format a retrieved memory as a markdown entry for CLAUDE.md.

    Args:
        memory: Memory dictionary with context, goal, decisions, etc.
        query: The search query that retrieved this memory.
        score: Optional similarity score.
        memory_id: Optional memory ID for reference.

    Returns:
        Formatted markdown string for the retrieved entry.
    """
    # Get date and time for header
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M")

    lines = [f"### {date_str}"]
    # The query is caller-supplied text, so it is sanitized like every other
    # interpolated value. It is NOT guarded by a truthiness test: an empty
    # query renders an empty pair of quotes, which is the pre-fix behaviour.
    lines.append(f"**Query**: \"{_sanitize_prompt_field(str(query or ''))}\"")

    if score is not None:
        lines.append(f"**Relevance**: {score:.2f}")

    # Add context if present.
    # THE HAND-ROLLED TRUNCATION THAT STOOD HERE IS GONE, AND ITS REMOVAL IS
    # PART OF THE FIX RATHER THAN A TIDY-UP. It cut to `context[:197] +
    # "..."`, and `_sanitize_prompt_field` at limit 200 cuts to
    # `cleaned[:197] + "..."`. Leaving both in place would cut the value
    # TWICE, to 194 characters. The helper output is byte-identical to the
    # code removed for a control-character-free input, so the truncation
    # behaviour at this site does not change; only the control-character
    # collapse and the outer strip are new.
    context = _sanitize_prompt_field(str(memory.get("context") or ""))
    if context:
        lines.append(f"**Context**: {context}")

    # Add goal if present
    goal = _sanitize_prompt_field(str(memory.get("goal") or ""))
    if goal:
        lines.append(f"**Goal**: {goal}")

    # Add memory ID if provided
    if memory_id:
        # AN IDENTIFIER, NOT FREE TEXT. The free-text bound of 200 is 3
        # times what the generator emits, and the store does not bound this
        # value at its ingress, so a caller-supplied id took the widest
        # bound in the classification.
        cleaned_id = _sanitize_prompt_field(
            str(memory_id), _REFRESH_IDENTIFIER_TRUNCATION_LIMIT
        )
        if cleaned_id:
            lines.append(f"**Memory ID**: {cleaned_id}")

    return "\n".join(lines)


def sync_retrieved_to_claude_md(
    memories: List[Dict[str, Any]],
    query: str,
    scores: Optional[List[float]] = None,
    memory_ids: Optional[List[str]] = None,
    claude_md_root: Optional[Path] = None
) -> SyncResult:
    """
    Sync retrieved memories to the Retrieved Context section of CLAUDE.md.

    Maintains a rolling window of the last 3 retrieved memories. New entries
    are added at the top of the section, and entries beyond MAX_RETRIEVED_MEMORIES
    are removed.

    Args:
        memories: List of memory dictionaries that were retrieved.
        query: The search query used.
        scores: Optional list of similarity scores (same order as memories).
        memory_ids: Optional list of memory IDs (same order as memories).
        claude_md_root: Declared containment anchor, exactly as on
            `sync_to_claude_md`. Omit it for today's behaviour.

    Returns:
        `SyncResult`. `bool()` of it is the value this function returned
        before the conversion below, and `.reason` says WHY when it is false.

    THIS IS THE SECOND AMBIENT WRITER AND IT HAD NO REFUSAL AT ALL. The save
    path at least had the `target` escape hatch; this one takes no target, so
    every call resolved ambiently with nothing standing between a test process
    and the operator's live file. It is reached from `PACTMemory.search()`
    whenever `sync_to_claude` is true, WHICH IS THE DEFAULT -- so an ordinary
    search was a write.

    ITS SIGNATURE WAS `bool` DELIBERATELY, AND THIS CONVERSION ANSWERS THAT
    DECISION RATHER THAN IGNORES IT. THE RECORDED PARAGRAPH CARRIED THREE
    CLAIMS AND TWO OF THEM NEED AN ANSWER HERE. The third, "this function
    is not being converted", was a statement of intent at the time, and the
    conversion settles it by being the act it describes, so it needs no
    separate answer. A reader who counts three and finds two answered has
    not met a claim that went missing.

    THE CONTINGENT ONE: "an annotation promising `SyncResult` here would
    describe code that returns `False`". That held only while the return
    sites stayed bare bools. ALL FIVE OF THEM ARE CONVERTED, so the
    annotation now describes the code and the cause is spent.

    THE OWNERSHIP ONE, WHICH THE CONVERSION DOES NOT TOUCH AND WHICH IS
    SUPERSEDED RATHER THAN DISCHARGED: the paragraph said the reason
    channel BELONGS to `sync_to_claude_md`. That was a true statement of
    the arrangement at the time and it is not contingent on this function.
    The architect superseded it: the channel is shared by both writers,
    because a caller of either one has the same need to separate a refusal
    from a no-op.

    WHY IT WAS WORTH CONVERTING, STATED WITHOUT OVERCLAIM. A REFUSED write and
    a DID-NOT-WRITE were one observation for every caller. THIS DOES NOT REPAIR
    A LIVE PRODUCTION OBSERVATION: the one production caller discards the
    return value, so no shipped code reads the bool today. What the conversion
    buys is CONSISTENCY with the sibling and a DIAGNOSTIC channel for a future
    caller and for the suite.

    NO TRUTHINESS READER CHANGES BEHAVIOUR, AND THAT IS NARROWER THAN "no
    caller". `SyncResult.__bool__` is `wrote`, so a truthiness read gets the
    value the bare bool gave. AN IDENTITY COMPARISON IS A DIFFERENT MATTER and
    `__bool__` cannot rescue it: `x is True` is False for an instance of this
    class however `bool(x)` reads. The suite held seven such comparisons and
    each one changed with this conversion.
    """
    if not memories:
        return SyncResult(SyncResult.EMPTY)

    # Same refusal as the save path, and the same exemptions: a declared anchor
    # is checked, so it is a stronger warrant than a named target. There is no
    # `target` parameter on this function, so the anchor is the ONLY way a test
    # process can legitimately drive it.
    _refuse_ambient_target_under_pytest(None, claude_md_root)

    claude_md_path, resolved_root = _resolve_display_claude_md_with_base()

    # Declared anchor replaces the containment base; it does not steer
    # resolution. The two Nones stay in separate variables for the same reason
    # they do in the sibling.
    project_root = (
        Path(claude_md_root) if claude_md_root is not None else resolved_root
    )

    if claude_md_path is None or project_root is None:
        logger.debug("CLAUDE.md not found, skipping retrieved context sync")
        return SyncResult(SyncResult.UNRESOLVED)

    # EXISTENCE GUARD. The `is None` check above is not sufficient: it covers a
    # resolver that finds NOTHING, not a resolver that returns a path to a file
    # that is not there. A TOTAL resolver never returns None, so it would pass
    # straight through into the lock and the read.
    #
    # ONE ROUTE, ONE MESSAGE. Unlike `sync_to_claude_md` this function takes no
    # explicit target, so there is no second way to arrive here and nothing to
    # differentiate -- the cause is always the ambient resolver. Do not
    # restructure it into a branch join to match its sibling: the asymmetry in
    # the two guards reflects a real asymmetry in the two signatures.
    #
    # WITHOUT THIS, AN ABSENT PATH DOES NOT MERELY LEAVE A LOCK SIDECAR -- IT
    # CREATES DIRECTORIES. `file_lock` makes the sidecar's parents, so a
    # resolved path three levels deep materialises the whole chain before the
    # read fails: `a/`, `a/b/`, `a/b/c/`, `a/b/c/.CLAUDE.md.lock`. Measured.
    # That is a write to a location the caller never named, on a path whose
    # only job was to be read.
    #
    # NAMES BOTH CAUSES, ASSERTS NEITHER: a file removed after it resolved is
    # indistinguishable here from a resolver that stopped being partial, and
    # the first is not a defect at all.
    if not claude_md_path.exists():
        logger.warning(
            "resolved display CLAUDE.md %s does not exist, skipping retrieved "
            "context sync (this never creates CLAUDE.md). Either the display "
            "resolver stopped returning only existing paths, or the file was "
            "removed after it resolved.", claude_md_path
        )
        return SyncResult(SyncResult.MISSING)

    try:
        # Serialize the FULL read-modify-write window under the shared sidecar
        # lock (see the "why lock the whole window" note above file_lock for the
        # read-under-lock / lock-identity / CLAUDE_PROJECT_DIR rationale).
        with file_lock(claude_md_path):
            # Read current content
            content = claude_md_path.read_text(encoding="utf-8")

            # Parse existing retrieved context section
            before_section, section_header, after_section, existing_entries = \
                _parse_retrieved_context_section(content)

            # Format new entries (only the top result to avoid clutter)
            new_entries = []
            top_memory = memories[0]
            score = scores[0] if scores else None
            memory_id = memory_ids[0] if memory_ids else None
            new_entry = _format_retrieved_entry(top_memory, query, score, memory_id)
            new_entries.append(new_entry)

            # Build new entries list: new entry first, then existing (up to max - 1)
            all_entries = new_entries + existing_entries
            trimmed_entries = all_entries[:MAX_RETRIEVED_MEMORIES]

            # Apply the PER-ENTRY token ceiling first, then the section
            # budget. THIS IS A SECOND CEILING SITE AND IT IS DIFFERENT CODE
            # FROM `_apply_token_budget`, which the Working Memory sync
            # calls. A ceiling placed only in that function reaches that
            # section alone and leaves this loop open. Each of the
            # MAX_RETRIEVED_MEMORIES entries gets an equal share here,
            # because this loop DROPS without compressing, so there is no
            # compressed-neighbour saving to redistribute.
            entry_ceiling = RETRIEVED_CONTEXT_TOKEN_BUDGET // MAX_RETRIEVED_MEMORIES
            trimmed_entries = [
                _apply_entry_token_ceiling(e, entry_ceiling) for e in trimmed_entries
            ]

            # Reduce entry count if over budget. Retrieved entries are
            # bounded per FIELD by `_format_retrieved_entry`; drop oldest
            # rather than compress. THE DROP-RATHER-THAN-COMPRESS CHOICE IS
            # DELIBERATE and the per-entry ceiling above is derived from it.
            # Subtract the popped entry's tokens instead of recalculating the full sum.
            total_tokens = sum(_estimate_tokens(e) for e in trimmed_entries)
            while len(trimmed_entries) > 1 and total_tokens > RETRIEVED_CONTEXT_TOKEN_BUDGET:
                removed = trimmed_entries.pop()
                total_tokens -= _estimate_tokens(removed)

            # Build new section content
            section_lines = [
                RETRIEVED_CONTEXT_HEADER,
                RETRIEVED_CONTEXT_COMMENT,
                ""  # Blank line after comment
            ]
            for entry in trimmed_entries:
                section_lines.append(entry)
                section_lines.append("")  # Blank line between entries

            section_text = "\n".join(section_lines)

            # Reconstruct file content
            if section_header:
                # Section existed, replace it
                # Ensure blank line before next section
                if after_section and not after_section.startswith("\n"):
                    new_content = before_section + section_text + "\n" + after_section
                else:
                    new_content = before_section + section_text + after_section
            else:
                # Section didn't exist, insert before Working Memory if it exists
                working_memory_match = re.search(
                    r'^## Working Memory',
                    content,
                    re.MULTILINE
                )
                if working_memory_match:
                    # Insert before Working Memory with blank line
                    insert_pos = working_memory_match.start()
                    new_content = content[:insert_pos] + section_text + "\n" + content[insert_pos:]
                else:
                    # Append at end
                    if not content.endswith("\n"):
                        content += "\n"
                    new_content = content + "\n" + section_text

            # Write back to file (atomic: temp + rename, so a crash mid-write
            # cannot leave the always-loaded CLAUDE.md truncated)
            _atomic_write_text(claude_md_path, new_content, project_root)

        logger.info("Synced retrieved memories to CLAUDE.md Retrieved Context section")
        return SyncResult(SyncResult.WROTE)

    except Exception as e:
        logger.warning(f"Failed to sync retrieved memories to CLAUDE.md: {e}")
        return SyncResult(SyncResult.FAILED)
