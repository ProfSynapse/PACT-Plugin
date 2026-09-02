"""
Location: pact-plugin/hooks/shared/backlog_store.py
Summary: READ side of the cross-session backlog — schema rules, file load,
         project resolution by path containment, the session-start block, and
         the total helper session_block() that converts every failure into a
         returned value.
Used by: hooks/session_init.py (session_block only) and hooks/shared/backlog.py
         (validate/load/find_for/file_local_flags, reused by the write side).

WHY THIS MODULE IS SEPARATE FROM backlog.py: the session-start read path must
issue no subprocess and no network call, and must not carry pact-memory in its
import closure. Keeping the two sides in one module and deferring the heavy
imports inside functions would hold today and rot tomorrow — a later edit
hoisting an import to module scope breaks the constraint with nothing going
red. A separate module makes the constraint structural. The dependency arrow is
one-way: backlog.py imports this module; this module imports backlog.py never.

NOTHING HERE MAY IMPORT pact-memory, subprocess, or any network client.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from .paths import get_backlog_dir

# Schema constants, shared with the write side so a writer cannot emit what a
# reader rejects.
SCHEMA_VERSION = 1
NOTE_MAX_CHARS = 200
MEMORY_MAX_IDS = 5
STATUSES = frozenset({"planned", "active", "blocked", "done"})
RELATIONAL_FIELDS = ("blocked_by", "batch_with", "exclusive_with")

# Item ids are exactly four lowercase hex characters, generated at creation and
# never reused, so the relational fields can point at something stable when a
# title is reworded.
# `\Z` rather than `$`: Python's `$` also matches before a trailing newline, so
# `$` would accept "ab12\n" from a hand-edited file.
_ITEM_ID = re.compile(r"^[0-9a-f]{4}\Z")

# How many planned items the session-start block names by title.
_BLOCK_PLANNED_LIMIT = 3

# How long a rendered title may be. A JUDGEMENT, not a measurement: its only
# anchor is coherence with NOTE_MAX_CHARS, since a title is a label rather than
# a sentence and so must bound tighter than a note. Anything in 80-150 is
# defensible; move it without re-deriving why it exists.
_TITLE_DISPLAY_MAX = 120

# Sort key for an item with no usable rank: rank orders planned items and is
# neither contiguous nor complete, so an unranked item sorts last rather than
# raising against an int.
_UNRANKED = float("inf")


class BacklogNotice(NamedTuple):
    """What session_init receives. Two independent fields, never one string
    plus a classifier.

    context: text for additionalContext; "" means nothing to say.
    alert:   text for systemMessage;     "" means nothing to say.

    The routing decision is already made by which field carries the value, so
    a caller has no text to inspect and the substring-matching router the
    design forbids is unconstructible rather than merely prohibited.
    """

    context: str
    alert: str


class BacklogFileError(Exception):
    """A specific backlog file could not be read, parsed, or validated.

    Carries the offending path so every loud message can name the file the
    reader must repair, whichever layer raised.
    """

    def __init__(self, path: Path, problem: str) -> None:
        super().__init__(f"{path}: {problem}")
        self.path = path
        self.problem = problem


class BacklogUnreadableError(BacklogFileError):
    """The BYTES could not be read — permission, a directory at the path, a
    lock, a transient IO failure. NOT a statement about the contents.

    Separate from its parent because the two answer different questions and
    one caller acts on the difference: `repair` MOVES the user's file, and
    "I could not read it" is not evidence of corruption. Collapsing them let a
    healthy backlog behind a permission bit present exactly as a corrupt one.

    A subclass rather than a sibling so every existing `except
    BacklogFileError` keeps catching both; only a caller that needs the
    distinction has to know it exists.
    """


def validate(obj: Any) -> List[str]:
    """Return a list of human-readable problems. An empty list means valid.

    Never raises, never mutates, never truncates. One validator serves both
    sides, so a writer cannot emit a file its own reader rejects.

    Dangling ids in the relational fields are deliberately NOT problems. They
    are reconciliation flags: a backlog carrying one is a backlog to report on,
    not a corrupt file to refuse.
    """
    problems: List[str] = []

    if not isinstance(obj, dict):
        return [f"top level is {type(obj).__name__}, expected an object"]

    if obj.get("version") != SCHEMA_VERSION:
        problems.append(
            f"version is {obj.get('version')!r}, this reader knows {SCHEMA_VERSION}"
        )

    for key in ("project", "project_path"):
        value = obj.get(key)
        if not isinstance(value, str) or not value:
            problems.append(f"{key} is {value!r}, expected a non-empty string")

    # `roots` is REQUIRED, with no optional-with-fallback branch. A fallback
    # would have to guess the missing checkouts, and the only guess available
    # is containment — the defect this field exists to remove. The writer
    # always emits at least project_root(), so an absent or empty roots means
    # the file was not written by this writer.
    roots = obj.get("roots")
    if not isinstance(roots, list) or not roots:
        problems.append(f"roots is {roots!r}, expected a non-empty list of paths")
    elif not all(isinstance(r, str) and r for r in roots):
        problems.append("roots holds a non-string or empty entry")
    elif not all(Path(r).is_absolute() for r in roots):
        # ABSOLUTE, for the same reason `plan` must be RELATIVE: a stored path
        # whose meaning depends on where the reader stands is not an identity.
        # The writer only ever records resolved absolute paths, so this can
        # arise from a hand-edited or corrupted file, which is the population
        # the read path exists to survive.
        #
        # THE RULE LIVES IN TWO PLACES ON PURPOSE, AND NEITHER IS REDUNDANT.
        # `_scan` DECLINES to match on a non-absolute root, which is what stops
        # a stored "." claiming whatever session happens to open in the
        # directory it resolves against. This rule REPORTS that root to the
        # user, which is what turns a file that silently stopped matching into
        # one whose problem is named. Delete this and the diagnosis goes;
        # delete the filter and the claim comes back.
        problems.append(f"roots holds a relative path: {roots!r}")

    items = obj.get("items")
    if not isinstance(items, list):
        return problems + [f"items is {type(items).__name__}, expected a list"]

    seen_ids = set()
    for index, item in enumerate(items):
        problems.extend(_validate_item(item, index, seen_ids))

    return problems


def _validate_item(item: Any, index: int, seen_ids: set) -> List[str]:
    """Schema rules for one item. `seen_ids` accumulates across the list so a
    duplicate id is reported on its second occurrence."""
    if not isinstance(item, dict):
        return [f"item {index} is {type(item).__name__}, expected an object"]

    problems: List[str] = []
    item_id = item.get("id")
    label = f"item {item_id!r}" if isinstance(item_id, str) else f"item {index}"

    if not isinstance(item_id, str) or not _ITEM_ID.match(item_id):
        problems.append(f"{label}: id is {item_id!r}, expected four hex characters")
    elif item_id in seen_ids:
        problems.append(f"{label}: id is a duplicate")
    else:
        seen_ids.add(item_id)

    status = item.get("status")
    if status not in STATUSES:
        problems.append(
            f"{label}: status is {status!r}, expected one of {sorted(STATUSES)}"
        )

    # Type only, deliberately no length rule: the length bound lives on the
    # RENDER path in _title. A rule here would produce a flag and nothing more,
    # since a validation failure no longer suppresses the block.
    title = item.get("title")
    if title is not None and not isinstance(title, str):
        problems.append(f"{label}: title is {type(title).__name__}, expected a string")

    note = item.get("note")
    if note is not None:
        if not isinstance(note, str):
            problems.append(f"{label}: note is {type(note).__name__}, expected a string")
        elif len(note) > NOTE_MAX_CHARS:
            problems.append(
                f"{label}: note is {len(note)} characters, limit is {NOTE_MAX_CHARS}"
            )

    memory = item.get("memory")
    if memory is not None:
        if not isinstance(memory, list):
            problems.append(
                f"{label}: memory is {type(memory).__name__}, expected a list"
            )
        elif len(memory) > MEMORY_MAX_IDS:
            problems.append(
                f"{label}: memory holds {len(memory)} ids, limit is {MEMORY_MAX_IDS}"
            )

    plan = item.get("plan")
    if plan is not None:
        if not isinstance(plan, str):
            problems.append(f"{label}: plan is {type(plan).__name__}, expected a string")
        elif Path(plan).is_absolute():
            problems.append(
                f"{label}: plan {plan!r} is absolute, expected a repo-relative path"
            )

    for field in RELATIONAL_FIELDS:
        value = item.get(field)
        if value is not None and not isinstance(value, list):
            problems.append(
                f"{label}: {field} is {type(value).__name__}, expected a list"
            )

    return problems


def read_json(path: Path) -> Dict[str, Any]:
    """Read and parse one backlog file, with no schema check.

    Raises BacklogFileError naming the path on an unreadable or unparseable
    file. Used by find_for, which needs only the stored project_path and must
    not reject a file for schema reasons before deciding whether it is even
    this project's file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # We READ the bytes and they are not text, so this is corruption rather
        # than an access failure. Caught explicitly because it is a ValueError
        # raised by the READ call: it is not an OSError, so the OSError clause
        # does not see it and it would escape read_json uncaught. Measured —
        # it crashed the CLI with a traceback before this clause existed.
        raise BacklogFileError(path, f"unparseable ({exc})") from exc
    except OSError as exc:
        raise BacklogUnreadableError(path, f"could not be read ({exc})") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise BacklogFileError(path, f"unparseable ({exc})") from exc
    # Valid JSON is not necessarily an object. Without this, a top-level list,
    # number or string reaches `.get()` in the scan and raises AttributeError,
    # which is NOT a BacklogFileError and so escapes the per-file catch there
    # into the generic handler — producing a message that names no file, where
    # the designed unreadable path names every offending one. One check routes
    # every caller, read side and write side alike, into the named-path path.
    if not isinstance(data, dict):
        raise BacklogFileError(
            path, f"top level is {type(data).__name__}, expected an object"
        )
    return data


# THERE IS DELIBERATELY NO read-parse-AND-VALIDATE HELPER HERE. One existed and
# was the single site that turned a validation failure into a BacklogFileError
# — the exception the CLI maps to its unreadable exit code, which the command
# file routes to `repair`, which MOVES THE USER'S FILE. Every caller had already
# moved to read_json + validate so the two dispositions stay separate, leaving
# it dead; deleting it makes "a merely non-conforming file cannot reach repair"
# a property of the code rather than a fact about today's callers.


def find_for(project_dir: str, backlog_dir: Path) -> Tuple[Optional[Path], List[Path]]:
    """The best match (or None) AND the files that could not be read.

    Thin face over _scan for callers that do not need the match count.
    """
    match, unreadable, _ = _scan(project_dir, backlog_dir)
    return match, unreadable


def _scan(
    project_dir: str, backlog_dir: Path
) -> Tuple[Optional[Path], List[Path], List[Path]]:
    """Locate this project's backlog by EXACT MEMBERSHIP in the stored `roots`.

    Returns the best match (or None), the files that could not be read, and
    EVERY file that claimed this project, best first.

    `roots` holds every checkout of the project — the main one and each
    worktree — as the writer resolved them. A file claims this session when
    `project_dir` IS one of them, or when the checkout ENCLOSING it is —
    `_enclosing_checkout` walks up to the nearest `.git`, so a session opened
    in a subdirectory of a recorded checkout matches, and one opened in a
    nested project that has its own `.git` does not.

    CONTAINMENT IS THE DEFECT, NOT THE FIX, AND "or under" IS CONTAINMENT
    RENAMED. A git repo at any ANCESTOR of another project claimed that
    project's sessions, which a dotfiles repo at $HOME makes the ordinary case
    rather than the exotic one: a store recording <tmp>/home surfaced its own
    active item into a session at <tmp>/home/Sites/unrelated-project. Exact
    membership declines that and keeps everything containment existed for,
    because a worktree path and the main root are BOTH `worktree ` lines and
    therefore both members.

    BOTH SIDES ARE RESOLVED before comparing: the writer stores paths that have
    been through `.resolve()`, so a lexical comparison against an unresolved
    `project_dir` compares different things the moment either crosses a
    symlink. On macOS `/var` is a symlink to `/private/var`, which makes that
    the default under any temporary directory. Resolution is a stat-level call
    — still no subprocess and no network.

    A CHECKOUT CREATED SINCE THE LAST WRITE is absent from `roots`, so its
    session finds no match and goes LOUD through the existing resolution-failure
    branch. That is the design working: the remedy that message names is itself
    a write, which refreshes `roots`. There is deliberately NO containment
    fallback for this case — it would reintroduce the defect verbatim.

    A project RENAME puts two files in the directory carrying the same roots —
    the old name and the new one — because the name derivation changed while
    the checkouts did not. The newer `updated` wins rather than whichever name
    sorts first, and the duplication is reported.

    AN UNREADABLE FILE NEVER ABORTS THE SCAN. The store is one flat directory
    shared by every project, so raising on the first bad file would let one
    project's corruption suppress another project's healthy block, and the
    chance of at least one bad file grows with every project the user touches.
    A file cannot be attributed to a project without parsing it, so ownership
    is not the rule: unreadable files are collected and returned, and the
    caller decides whether they are the loud reason or a note beside a block.
    Matching on the FILENAME would sidestep the parse, and it is shut for a
    second reason — it would make the read path derive a project name, and
    deriving no name at all is what removes the hazard of a duplicate
    derivation entirely.

    A directory-level failure still raises, so this never swallows an error
    that genuinely aborts the scan.
    """
    target = _resolved(Path(project_dir))
    # Computed ONCE. It depends only on `target`, so re-walking it per file was
    # one filesystem walk per backlog in the store for an unchanging answer.
    enclosing = _enclosing_checkout(target)
    found = []
    unreadable: List[Path] = []

    for path in sorted(backlog_dir.glob("*.json")):
        try:
            data = read_json(path)
        except BacklogFileError:
            unreadable.append(path)
            continue
        roots = data.get("roots")
        if not isinstance(roots, list):
            continue
        # NON-ABSOLUTE ROOTS ARE FILTERED HERE, NOT LEFT TO validate().
        # validate() runs on the file ALREADY SELECTED, so the rule was
        # enforced downstream of the decision it governs: a stored `"."`
        # resolved against the process working directory and CLAIMED whatever
        # session happened to open there, rendering another project's items
        # with a conformance note beside them.
        #
        # This is not the silent-skip that keeping the rule in validate() was
        # meant to avoid. Skipping a legitimate root would hide a real match;
        # a relative root IDENTIFIES NOTHING, because its meaning depends on
        # where the reader stands, so declining to match on it withholds no
        # identity. A file whose roots are ALL relative therefore never
        # matches — and it is not invisible: no match means the existing loud
        # resolution failure fires, and `/PACT:next` still finds the file by
        # name and reports the relative root as a schema problem.
        #
        # A malformed entry yields an empty set: no match, same loud path. No
        # new raise site, so the totality boundary does not move.
        recorded = {
            _resolved(Path(r))
            for r in roots
            if isinstance(r, str) and Path(r).is_absolute()
        }
        if target not in recorded and enclosing not in recorded:
            continue
        found.append((str(data.get("updated") or ""), path))

    found.sort(reverse=True)
    matched = [path for _, path in found]
    return (matched[0] if matched else None), unreadable, matched


def _enclosing_checkout(path: Path) -> Optional[Path]:
    """The nearest ancestor holding a `.git`, or None.

    THIS IS NOT CONTAINMENT RE-ADMITTED, and that is the only question worth
    asking about it. A genuine subdirectory of a checkout and an unrelated
    project nested under one are INDISTINGUISHABLE BY PATH SHAPE — both are "a
    directory under a recorded root" — which is exactly why containment cannot
    come back in any form, including one wearing a different noun.

    `.git` is the discriminator the path itself does not carry. An unrelated
    project HAS one, so its enclosing checkout is ITSELF and is not in `roots`,
    and it is declined. A genuine subdirectory has none, so the walk continues
    up to the checkout that DOES, which IS in `roots`. Same signal git uses,
    read by stat rather than by subprocess.

    The rung exists because CLAUDE_PROJECT_DIR really does point at in-repo
    subdirectories: measured across recorded session contexts, one names a
    path ending `/pact-plugin`, which is TRACKED repo content and so could
    never have been a worktree root. Exact membership alone declined those
    sessions, and the loud state could not self-heal, because the porcelain
    that refreshes `roots` never emits a subdirectory.

    `.exists()` on an unreadable path returns False rather than raising, so
    this adds no raise site and the totality boundary does not move.
    """
    for directory in [path, *path.parents]:
        if (directory / ".git").exists():
            return directory
    return None


def _items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The item dicts, or NONE when `items` is not a list.

    `data.get("items") or []` returns THE VALUE when it is truthy, so a
    non-list `items` reaches the `for` and raises TypeError on a file that
    parses. Both readers of `items` run on data validate() has already
    rejected, where fields arrive unchecked, so the type is tested rather than
    assumed — the docstrings said so and the code did not.

    The guard belongs here rather than at either call site: the READ path is
    already protected upstream by session_block's render gate, but reconcile()
    on the write side is not, and both route through this function.
    """
    value = data.get("items")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _resolved(path: Path) -> Path:
    """Absolute, symlink-free form, or the path unchanged when it will not
    resolve. Never raises, so a comparison is always well defined."""
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def file_local_flags(data: Dict[str, Any]) -> List[str]:
    """Drift visible in the file alone, with no git, tracker or store lookup.

    Three of the drift classes are decidable from the file's own contents, and
    those three are the only ones the read path may compute: a relational field
    naming an unknown id, a blocked_by naming an item already done, and two
    mutually exclusive items both active right now. Every other class needs an
    external source and belongs to the reconciliation path.

    Shared with the write side so both surfaces report the same file-local
    drift rather than growing two answers to one question.

    EVERY relational field is read through _relation_ids, because this function
    now runs on data validate() has already REJECTED: rendering a
    non-conforming file means its fields arrive unchecked.
    """
    items = _items(data)
    by_id = {item.get("id"): item for item in items if isinstance(item.get("id"), str)}
    flags: List[str] = []

    for item in items:
        label = _label(item)
        for field in RELATIONAL_FIELDS:
            ids, malformed = _relation_ids(item, field, label)
            flags.extend(malformed)
            for other in ids:
                if other not in by_id:
                    flags.append(f"{label}: {field} names unknown id {other!r}")
                elif field == "blocked_by" and by_id[other].get("status") == "done":
                    flags.append(
                        f"{label}: blocked_by names {_label(by_id[other])}, already done"
                    )

    for item in items:
        if item.get("status") != "active":
            continue
        # The malformed flags are DISCARDED here: this field was already read
        # in the loop that precedes this one, and reporting it twice would
        # double-count one defect in the block's flag count.
        ids, _ = _relation_ids(item, "exclusive_with", _label(item))
        for other in ids:
            peer = by_id.get(other)
            if peer is not None and peer.get("status") == "active":
                if _label(item) < _label(peer):  # report each pair once
                    flags.append(
                        f"{_label(item)} and {_label(peer)} are exclusive and both active"
                    )

    return flags


def _relation_ids(
    item: Dict[str, Any], field: str, label: str
) -> Tuple[List[str], List[str]]:
    """Usable ids from one relational field, plus flags for what was dropped.

    TWO RAISES LIVE HERE WITHOUT THIS GUARD, and both became reachable when the
    read path began rendering files that failed validate(): a truthy
    non-iterable field raises on iteration, and an unhashable entry (a dict, a
    list) raises on the `in by_id` membership test. Either one is caught by
    session_block's outer handler, so totality holds — but the OUTCOME is that
    the block and its named conformance note are both replaced by a read
    failure naming no file, which is the state the named-path work exists to
    prevent.

    Ids are strings by schema, so a non-string entry could never match one; it
    is dropped rather than compared. Dropping is REPORTED rather than silent,
    because a non-conforming file is exactly what the render path now shows and
    says so about.

    The guard lives here rather than in validate() for the reason that settled
    the title-length question: a validate() failure no longer suppresses the
    block, so a rule there yields a flag and defends nothing on this path.
    """
    value = item.get(field)
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], [f"{label}: {field} is {type(value).__name__}, expected a list"]
    ids = [entry for entry in value if isinstance(entry, str)]
    dropped = len(value) - len(ids)
    if not dropped:
        return ids, []
    # Noun-only phrasing: no verb, so nothing has to agree with the count.
    return ids, [
        f"{label}: {field} holds {dropped} non-id entr{'y' if dropped == 1 else 'ies'}"
    ]


def format_block(data: Dict[str, Any], context_anchor: Optional[float] = None) -> str:
    """The session-start block: active work, the next few planned by rank, and
    a count of file-local drift. Never the whole list — a block that grows with
    the backlog becomes noise and gets skimmed.

    `context_anchor` is UNIX epoch SECONDS for when the context was last
    populated from scratch, or None. Passed rather than imported: this module
    deliberately excludes session_init from its import closure.
    """
    items = _items(data)
    active = [item for item in items if item.get("status") == "active"]
    planned = sorted(
        (item for item in items if item.get("status") == "planned"),
        key=_rank_key,
    )[:_BLOCK_PLANNED_LIMIT]
    flags = file_local_flags(data)

    lines = [f"PACT backlog ({data.get('project')}):"]
    if active:
        lines.append("  active: " + "; ".join(_title(item) for item in active))
    if planned:
        lines.append("  next: " + "; ".join(_title(item) for item in planned))
    if not active and not planned:
        lines.append("  nothing active or planned")
    if flags:
        lines.append(f"  {len(flags)} flagged — run /PACT:next for the detail")
    age = _age_line(data, context_anchor)
    if age:
        lines.append(age)
    return "\n".join(lines)


def _age_line(data: Dict[str, Any], context_anchor: Optional[float]) -> str:
    """One line when the backlog has not been written since the context was
    last populated from scratch, otherwise "".

    REPORTS THE OBSERVATION, NOT A DIAGNOSIS. "Nothing written since" cannot
    separate a write mechanism that stopped from a caller that skipped its
    write, and both are worth surfacing, so it says what is true and claims
    no cause.

    With NO anchor this renders nothing rather than falling back to a
    fabricated left-hand side. The caller gates on the TRIGGER — whether this
    is a context reset — never on this value's null-ness: `compact` is not a
    consuming source, so a compact-only journal yields None, and a
    render-when-not-None rule would miss the primary re-injection trigger while
    firing on every resume, which is not a re-injection at all.
    """
    if context_anchor is None:
        return ""
    written = _as_epoch(data.get("updated"))
    if written is None or written >= context_anchor:
        return ""
    return (
        f"  nothing written to the backlog since this context was built "
        f"(last write {data.get('updated')})"
    )


def _as_epoch(value: Any) -> Optional[float]:
    """UNIX seconds for a stored UTC ISO-8601 stamp, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def session_block(
    project_dir: str,
    backlog_dir: Optional[Path] = None,
    context_anchor: Optional[float] = None,
) -> BacklogNotice:
    """THE TOTAL HELPER. Every state is a return value; nothing raises.

    An exception escaping here does not surface a message — it reaches
    session_init's outer handler, which discards the accumulated context parts
    and emits a safety net instead, destroying the plugin banner and the
    pin-slot line along with anything this module wanted to say. So loudness is
    CONSTRUCTED, as a returned string, and never raised.

    The boundary is the outermost call and cannot be drawn any further in:
    Path.home(), the directory listing, every read and every parse can raise,
    so a boundary one call deeper leaves a raising call outside it.

    States:
      backlog dir absent, or present and empty  -> ("", "")
      one entry matches and validates           -> (block, "")
      a match PLUS unreadable files             -> (block + note, note)
      a match that does not CONFORM             -> (block + note, note)
      a match whose `items` is not a list       -> loud, names the file
      no match, unreadable files seen           -> loud, names those files
      no match, all files readable              -> loud, resolution failure
      project_dir empty or relative             -> loud, names the cause
      anything unexpected                       -> loud, names the exception

    The two block-plus-note rows are the only ones quiet and loud at once, and
    their channels are ASYMMETRIC: `context` carries the block and the notes,
    `alert` carries the notes alone. The block is not news to the user; the bad
    file is, and the user is the only party who can authorise a repair. Putting
    a note only in `context` would leave the problem visible to the
    orchestrator and invisible to the one person able to act.

    This state repeats every session until the file is repaired, and that is
    correct rather than a defect. A correction must outlive the belief it
    corrects, so there is deliberately no suppress-after-first-seen rule.

    Residual, stated rather than implied: `except Exception` does not catch
    BaseException, so KeyboardInterrupt and MemoryError still cross. That
    matches session_init's own handler, and swallowing an interrupt during a
    dying session would be the worse trade.
    """
    try:
        if not project_dir or not Path(project_dir).is_absolute():
            return _loud(
                f"PACT backlog: cannot resolve a backlog because the project "
                f"directory is {project_dir!r}, which is not an absolute path. "
                f"No backlog was read. Nothing is wrong with the store."
            )

        root = get_backlog_dir() if backlog_dir is None else backlog_dir
        if not root.is_dir():
            return BacklogNotice("", "")

        entries = sorted(root.glob("*.json"))
        if not entries:
            return BacklogNotice("", "")

        match, unreadable, claimants = _scan(project_dir, root)
        notes = []
        if unreadable:
            notes.append(
                "PACT backlog: could not read "
                + ", ".join(str(path) for path in unreadable)
                + ". Nothing was modified — this path only reads. Run /PACT:next, "
                "which reports what it can do with each one."
            )

        if match is None:
            if notes:
                return _loud(notes[0])
            return _loud(
                f"PACT backlog: {len(entries)} backlog file(s) under {root}, and "
                f"none records {project_dir} as a checkout root. This is a "
                f"resolution failure, NOT an empty backlog — do not treat this "
                f"project as having no backlog. A checkout created since the "
                f"last write is not yet recorded; /PACT:next writes, which "
                f"records it."
            )

        # NON-CONFORMANCE IS NOT CORRUPTION. Corruption is "I cannot understand
        # this" and justifies replacing the block; a rule violation is "I
        # understand it and it breaks a rule I now enforce" and does not. So
        # the block renders from a non-conforming file and the problems are
        # reported beside it. The isinstance gate is load-bearing, for a
        # NARROWER class than "not a list": format_block coerces the item
        # fields IT renders — title, id and rank — and its `or []` absorbs any
        # falsy `items`, so what actually raises HERE is
        # a TRUTHY NON-ITERABLE. Measured — 5, 3.5 and True raise TypeError,
        # while "not a list", {"a": 1}, (1, 2), b"bytes" and None all render
        # cleanly. Pick a truthy non-iterable when testing this branch: a
        # string is a non-list scalar that does NOT raise, so an arm built on
        # one passes with the gate removed. This gate covers `items` ONLY; the
        # relational fields are read by file_local_flags and carry their own
        # guard in _relation_ids.
        data = read_json(match)
        problems = validate(data)
        if problems and not isinstance(data.get("items"), list):
            raise BacklogFileError(match, "; ".join(problems))
        if problems:
            notes.append(
                f"PACT backlog: {match} does not conform ({'; '.join(problems)}). "
                f"The block is rendered from it anyway and nothing was modified."
            )

        block = format_block(data, context_anchor)
        if len(claimants) > 1:
            # THE CAUSE IS NOW DETERMINATE, so name it. Under containment this
            # sentence was silent about cause, because an ANCESTOR repo produced
            # the same state with both files legitimate and belonging to
            # different projects — naming a cause there would have sent a reader
            # to merge two backlogs that must stay separate. Exact membership
            # removes that case: two files can only share a checkout root by a
            # rename or a double write, and both mean one file is stale.
            block += (
                f"\n  {len(claimants)} stored backlogs record this checkout: "
                + ", ".join(path.name for path in claimants)
                + f". Reading {match.name} (most recently updated). A rename or "
                f"a double write left the other behind; run /PACT:next to "
                f"reconcile them."
            )
        if notes:
            # Quiet and loud at once: the block goes only to context, the notes
            # go to both, so the user sees what only they can act on.
            joined = "\n  ".join(notes)
            return BacklogNotice(f"{block}\n  {joined}", joined)
        return BacklogNotice(block, "")

    except BacklogFileError as exc:
        return _loud(
            f"PACT backlog: {_safe_detail(exc)}. The file was NOT modified — this "
            f"path only reads. Run /PACT:next, which reports what it can do "
            f"with it."
        )
    except Exception as exc:  # total helper: every state is a value, never a raise
        return _loud(
            f"PACT backlog: could not be read "
            f"({type(exc).__name__}: {_safe_detail(exc)}). Nothing was modified."
        )


def _safe_detail(exc: BaseException) -> str:
    """`str(exc)`, or a type-only stand-in when the exception will not print.

    An exception whose own `__str__` raises must not escape the helper whose
    entire contract is that nothing escapes. `repr()` is no safer — `__repr__`
    can raise too — so the fallback names the type, which is a class attribute
    lookup and cannot raise. Shared by both handlers so the guarantee is in one
    place: the corrupt-file handler still gets to name WHICH file, which is the
    only actionable content in that message.
    """
    try:
        return str(exc)
    except Exception:
        return f"<unprintable {type(exc).__name__}>"


def _loud(message: str) -> BacklogNotice:
    """Both channels carry the same string. additionalContext is ungated and
    survives compaction, so the correction outlives the belief it corrects;
    systemMessage is the only channel the user sees, and the user is the only
    party who can authorise a repair. The source gate on systemMessage lives at
    the call site, which already holds `source`.
    """
    return BacklogNotice(context=message, alert=message)


def _label(item: Dict[str, Any]) -> str:
    return str(item.get("id") or item.get("title") or "?")


def _title(item: Dict[str, Any]) -> str:
    """The item's title as ONE capped line, for the session-start block.

    FLATTENING IS THE SECURITY HALF and it has no tunable parameter: the block
    is line-structured, and a title carrying a newline can forge a second
    `active:` line or a role marker into session-start context. `split()` on no
    argument splits on every whitespace class, so the rejoin removes newlines,
    carriage returns and tabs together and collapses runs.

    Capping is noise control, a different job with an arbitrary number. Both
    live here rather than in validate() because an over-long or multi-line
    title is non-conformance, not corruption, and must not take the loud path.
    """
    text = " ".join(str(item.get("title") or item.get("id") or "?").split())
    if len(text) <= _TITLE_DISPLAY_MAX:
        return text or "?"
    return text[: _TITLE_DISPLAY_MAX - 1] + "…"


def _rank_key(item: Dict[str, Any]) -> float:
    rank = item.get("rank")
    return float(rank) if isinstance(rank, (int, float)) else _UNRANKED
