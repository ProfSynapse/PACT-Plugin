#!/usr/bin/env python3
"""Report which agent-memory leaf files no index still points at.

Location: pact-plugin/scripts/memory_reachability.py

Summary: An agent's memory index is truncated before it is loaded, so a pointer
that falls past the cut is on disk and out of context. An index rewrite that
drops a pointer leaves the leaf fully written and unfindable. Nothing detected
either. This tool reads one agent-memory directory and reports both.

READ-ONLY BY CONSTRUCTION. There is no write path: no open-for-write, no
tempfile, no replace, no lock. With --emit-edit it PRINTS an edit block for an
agent to apply with its own editing tool, which is the mechanism the index
upkeep rule already mandates. Rebuilding that inside a script was the earlier
design and it was the problem, not the solution.

WHY THE MATCH RULE IS A BARE TOKEN AND NOT A LINK PARSER. A pointer with no
syntax at all appears in real indexes -- a comma-separated word in a satellite
naming a leaf's frontmatter `name:`. With nothing to key on, no link parser can
be shown complete, so no test could certify one. Matching a bounded bare token
against four keys subsumes every link spelling because each one CONTAINS one of
the keys, and it matches what an agent can actually act on.

DO NOT RE-DERIVE THE REACHABILITY RULE. Four independent derivations of the one
English sentence describing it produced four different orphan counts. Every
difference sat in a detail the sentence did not pin: a first-token frontmatter
parse, a separator, a boundary character class, a key set. The rule is spelled
out in KEY/NORMALISE/MATCH below and each clause is load-bearing.

Usage:
  python3 memory_reachability.py <directory>
  python3 memory_reachability.py <directory> --report out.json
  python3 memory_reachability.py <directory> --quiet --emit-edit

Exit codes:
  0 -- the scan finished. FINDINGS DO NOT CHANGE IT: this tool annotates and
       the caller decides. A directory holding no index is not_applicable,
       which is neither an error nor a fully-orphaned directory.
  2 -- a precondition failed and nothing was scanned.
  There is no third code, because there is no write to fail.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

INDEX_NAME = "MEMORY.md"

# An index-shaped file: the index itself, a satellite, or an archive. Used to
# decide what MAY become a root, never to decide what IS one -- roots are found
# by FOLLOWING POINTERS, never by globbing this pattern. An unnamed satellite is
# genuinely unreachable, and globbing promotes it to a root, certifying its
# targets and hiding the one file that would have led anyone to the problem.
INDEX_SHAPED = ("MEMORY-", "INDEX_", "ARCHIVE")

# A root that represents retired content. A leaf reachable ONLY through one of
# these is archive_only, not an orphan -- that is compaction working as designed,
# and collapsing the two condemns it for behaving correctly.
ARCHIVE_MARKERS = ("archive", "pre-compact", "precompact")

# The type prefixes a leaf filename may carry. Exactly ONE is stripped, never
# recursively: recursive stripping manufactures keys like `patterns` and `drift`
# that match ordinary index prose and silently certify unreachable files.
TYPE_PREFIXES = ("feedback_", "project_", "reference_", "user_")

# The platform truncates the index before loading it. Lines are cut first, then
# size, and the size cut snaps back to the last newline.
MAX_LINES = 200
MAX_UNITS = 25000

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
# WHOLE LINE TO END, never `(\S+)`. A first-token parse truncates at the first
# space, and a fifth of real leaves carry a value containing whitespace -- which
# leaves keys like `pr` and `497` that match anything.
_NAME_FIELD = re.compile(r"^name:\s*(.+?)\s*$", re.M)

# An index entry line: a markdown list item. Used only to find the emission
# neighbour, never for reachability.
_ENTRY_LINE = re.compile(r"^\s*[-*]\s+\S")


class Scan(NamedTuple):
    """The result. Named fields so `len()` on it is unwritable rather than discouraged."""

    directory: Path
    not_applicable: bool
    roots: Tuple[Path, ...]
    live_reachable: Tuple[Path, ...]
    archive_only: Tuple[Path, ...]
    unreachable: Tuple[Path, ...]
    past_the_cut: Tuple[Path, ...]
    bare_token_only: int
    unreached_index_files: Tuple[Path, ...]


class PreconditionError(Exception):
    """Nothing was scanned."""


def normalise(text: str) -> str:
    """Lowercase and map hyphen to underscore. NO space normalisation.

    Applied to BOTH key and haystack. Space normalisation was measured and it
    over-credits: it turns prose into underscored tokens and manufactures hits.
    """
    return text.replace("-", "_").lower()


def utf16_units(text: str) -> int:
    """Measure text in the unit the index-upkeep rule states its size limit in.

    That rule is the single source for the unit and the ceiling; this function
    deliberately restates neither. `len()` is the wrong instrument -- it counts
    characters, and undercounts every astral one.
    """
    return len(text.encode("utf_16_le")) // 2


def truncate_as_loaded(text: str) -> str:
    """The prefix of an index that actually reaches an agent's context.

    Lines are cut before size, and the size cut snaps back to the last newline
    so the loaded text is a line-aligned prefix.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) > MAX_LINES:
        text = "".join(lines[:MAX_LINES])
    if utf16_units(text) <= MAX_UNITS:
        return text
    cut = text
    while cut and utf16_units(cut) > MAX_UNITS:
        cut = cut[: len(cut) - 1]
    newline = cut.rfind("\n")
    return cut[: newline + 1] if newline != -1 else cut


def is_index_shaped(path: Path) -> bool:
    return path.name == INDEX_NAME or path.name.startswith(INDEX_SHAPED)


def is_archive(path: Path) -> bool:
    return any(marker in path.stem.lower() for marker in ARCHIVE_MARKERS)


def keys_for(path: Path) -> List[str]:
    """Every string that may stand for this file in an index, normalised.

    Four keys. The frontmatter one carries roughly a fifth of real pointers on
    its own, and stripping one type prefix carries pointers written as the bare
    topic. Both were measured to move the count; neither is speculative.
    """
    found = {path.name, path.stem}
    for prefix in TYPE_PREFIXES:
        if path.stem.startswith(prefix):
            found.add(path.stem[len(prefix):])
            break
    match = _FRONTMATTER.match(_read(path))
    if match:
        name = _NAME_FIELD.search(match.group(1))
        if name:
            found.add(name.group(1).strip().strip("\"'"))
    return [normalise(key) for key in found if key]


def mentions(haystack: str, key: str) -> bool:
    """True when `key` appears in `haystack` as a bounded bare token.

    `re.escape` is not hardening: real frontmatter names carry regex-special
    characters, and an unescaped `+` silently becomes a quantifier. The boundary
    classes are spelled out rather than `\\w` because a preceding dot or hyphen
    must NOT count as a boundary -- otherwise a key matches inside a longer
    dotted token.
    """
    return re.search(
        r"(?<![A-Za-z0-9_.-])" + re.escape(key) + r"(?![A-Za-z0-9_-])",
        haystack,
        re.IGNORECASE,
    ) is not None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_roots(directory: Path) -> Tuple[Path, ...]:
    """The index, plus index-shaped files named in any root, to a FIXED POINT.

    Not one level: a satellite naming another satellite is live in real trees.
    """
    index = directory / INDEX_NAME
    roots = {index}
    while True:
        blob = normalise("\n".join(_read(path) for path in sorted(roots)))
        found = {
            path
            for path in directory.glob("*.md")
            if is_index_shaped(path) and mentions(blob, normalise(path.name))
        }
        if found <= roots:
            return tuple(sorted(roots))
        roots |= found


def scan(directory: Path) -> Scan:
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        raise PreconditionError("not a directory: {0}".format(directory))
    if not (directory / INDEX_NAME).is_file():
        return Scan(directory, True, (), (), (), (), (), 0, ())

    roots = find_roots(directory)
    live_roots = [path for path in roots if not is_archive(path)]

    def haystack(paths: Sequence[Path], truncated: bool) -> str:
        parts = [_read(path) for path in paths]
        if truncated:
            parts = [truncate_as_loaded(part) for part in parts]
        return normalise("\n".join(parts))

    all_blob = haystack(roots, False)
    live_blob = haystack(live_roots, False)
    loaded_blob = haystack(roots, True)
    # Link syntax stripped, so what remains is prose only. Its complement is the
    # text inside links. A leaf hit ONLY in the prose half is carried by a bare
    # token, which is the diagnostic for whether the verdict rests on coincidence.
    prose_blob = normalise(re.sub(r"\[\[[^\]]*\]\]|\[[^\]]*\]\([^)]*\)|`[^`]*`", " ", "\n".join(_read(p) for p in roots)))

    leaves = [
        path
        for path in sorted(directory.glob("*.md"))
        if path not in roots and path.name != INDEX_NAME
    ]

    live, archived, unreachable, past_cut, bare_only = [], [], [], [], 0
    for leaf in leaves:
        leaf_keys = keys_for(leaf)
        if any(mentions(live_blob, key) for key in leaf_keys):
            live.append(leaf)
            if not any(mentions(loaded_blob, key) for key in leaf_keys):
                past_cut.append(leaf)
            if any(mentions(prose_blob, key) for key in leaf_keys) and not any(
                mentions(all_blob, key) for key in leaf_keys if not mentions(prose_blob, key)
            ):
                bare_only += 1
        elif any(mentions(all_blob, key) for key in leaf_keys):
            archived.append(leaf)
        else:
            unreachable.append(leaf)

    # glob-versus-follow: an index-shaped file on disk that no root names. Zero is
    # the expected reading, which is exactly why it must still be printed.
    unreached = tuple(
        path for path in sorted(directory.glob("*.md")) if is_index_shaped(path) and path not in roots
    )
    return Scan(
        directory, False, roots, tuple(live), tuple(archived), tuple(unreachable),
        tuple(past_cut), bare_only, unreached,
    )


def emit_edit(result: Scan, heading: Optional[str] = None) -> Optional[str]:
    """An edit block placing a pointer for each unreachable leaf.

    ANCHORED ON THE INSERTION NEIGHBOUR -- the last entry line inside the loaded
    prefix -- never on a section heading. A heading is already unique, so
    uniqueness expansion never fires for it, and the pointer then lands directly
    after the heading when it belonged at the section's end. Naming a line that
    is already there makes placement exact by construction instead of inferred.

    The anchor is verified unique against the RAW file text and expanded with
    preceding lines until it is, so the editing tool's not-unique failure is
    unreachable and the agent never arrives at the moment where a replace-all
    flag looks like the answer. Expansion is the FALLBACK for a duplicated entry
    line, not the mechanism.
    """
    if result.not_applicable or not result.unreachable:
        return None
    index = result.directory / INDEX_NAME
    raw = _read(index)
    lines = raw.splitlines()
    # Inside the loaded prefix only: a pointer past the cut is written and never
    # read, which is the second failure this tool exists to report.
    loaded = len(truncate_as_loaded(raw).splitlines())

    if heading is None:
        # No section named: the tail of the loaded prefix. Never past the cut,
        # where a pointer is written and never read.
        entries = [i for i, line in enumerate(lines[:loaded]) if _ENTRY_LINE.match(line)]
        if not entries:
            return ("REFUSED: {0} has no entry line anywhere in its loaded prefix, so "
                    "there is nothing to anchor on. Add the first pointer by hand, then "
                    "re-run.".format(index))
        end = entries[-1]
    else:
        where = [i for i, line in enumerate(lines) if line.strip() == heading.strip()]
        if not where:
            return "REFUSED: no line in {0} reads {1!r}.".format(index, heading)
        top = where[0]
        if top >= loaded:
            return ("REFUSED: the section {0!r} in {1} begins past the loaded prefix, so a "
                    "pointer placed there would be written and never read — the condition "
                    "this tool reports. Name a section nearer the head, or omit the heading "
                    "to place at the end of the prefix.".format(heading, index))
        # The section's last entry line, bounded by the next heading. An EMPTY
        # section anchors on the heading itself: with no entries to land in front
        # of, "after the heading" and "at the section's end" are one position.
        end = top
        for i in range(top + 1, min(loaded, len(lines))):
            if lines[i].lstrip().startswith("#"):
                break
            if _ENTRY_LINE.match(lines[i]):
                end = i

    start = end
    while raw.count("\n".join(lines[start:end + 1])) > 1:
        if start == 0:
            return "REFUSED: could not make the anchor unique in {0}.".format(index)
        start -= 1
    anchor = "\n".join(lines[start:end + 1])
    # The matching predicate lowercases and maps hyphens; text taken from that
    # normalised haystack would never match the real file, and would pass any
    # fixture that is already lowercase ASCII. This is the only check that
    # catches that vacuous green.
    if anchor not in raw:
        return "REFUSED: anchor is not a byte-exact slice of {0}.".format(index)

    pointers = "\n".join(
        "- [{0}]({1}) — RESTORED, describe and re-file".format(leaf.stem, leaf.name)
        for leaf in result.unreachable
    )
    return (
        "Apply with your editing tool against {0}, exactly once:\n\n"
        "old_string:\n{1}\n\n"
        "new_string:\n{1}\n{2}\n\n"
        "The file may have changed since this was computed. The edit fails on "
        "no-match rather than landing wrongly; if it fails, STOP and re-run this "
        "tool rather than broadening the match.".format(index, anchor, pointers)
    )


def render(result: Scan) -> str:
    if result.not_applicable:
        return "swept {0}\n  no {1} -- not applicable (this is not an orphaned directory)".format(
            result.directory, INDEX_NAME
        )
    return "\n".join([
        "swept {0}".format(result.directory),
        "  roots (followed, never globbed): {0}".format(len(result.roots)),
        "  live-reachable  {0}".format(len(result.live_reachable)),
        "  archive-only    {0}   (a real pointer through a named archive)".format(len(result.archive_only)),
        "  unreachable     {0}".format(len(result.unreachable)),
        "  past-the-cut    {0}   (pointed at, but past the loaded prefix)".format(len(result.past_the_cut)),
        "  diagnostic: verdict carried by a bare token only: {0}".format(result.bare_token_only),
        "  diagnostic: index-shaped files no root names: {0}".format(len(result.unreached_index_files)),
        "  keys: filename | stem | whole-line frontmatter name: | stem minus one type prefix",
        "  match: bounded bare token, case-insensitive, hyphen and underscore equivalent",
    ] + ["    unreachable: {0}".format(leaf.name) for leaf in result.unreachable])


def as_dict(result: Scan) -> dict:
    return {
        "directory": str(result.directory),
        "not_applicable": result.not_applicable,
        "roots": [p.name for p in result.roots],
        "live_reachable": [p.name for p in result.live_reachable],
        "archive_only": [p.name for p in result.archive_only],
        "unreachable": [p.name for p in result.unreachable],
        "past_the_cut": [p.name for p in result.past_the_cut],
        "bare_token_only": result.bare_token_only,
        "unreached_index_files": [p.name for p in result.unreached_index_files],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("directory", help="one agent-memory directory to scan (no default)")
    parser.add_argument("--report", help="write the findings to this JSON file")
    parser.add_argument("--quiet", action="store_true", help="suppress the text report")
    parser.add_argument(
        "--emit-edit",
        nargs="?",
        const="",
        default=None,
        metavar="HEADING",
        help="print an edit block restoring pointers; this tool never writes. "
             "Give a heading to place them in that section — choosing the section is a "
             "judgement about topic, which is yours and not the tool's. Omitted, they go "
             "at the end of the part of the index that actually loads.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = scan(Path(args.directory))
    except PreconditionError as exc:
        print("memory_reachability REFUSED: {0}".format(exc), file=sys.stderr)
        return 2
    if args.report:
        out = Path(args.report).expanduser().resolve()
        if out.parent == result.directory.resolve():
            print("memory_reachability REFUSED to write the report into the scanned "
                  "directory: {0}".format(out), file=sys.stderr)
            return 2
        out.write_text(json.dumps(as_dict(result), indent=2, sort_keys=True), encoding="utf-8")
    if not args.quiet:
        print(render(result))
    if args.emit_edit is not None:
        block = emit_edit(result, args.emit_edit or None)
        print("\n" + block if block else "\nno unreachable files; nothing to emit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
