#!/usr/bin/env python3
"""
Find memory records whose list fields hold shredded prose.

Location: pact-plugin/scripts/memory_repair/shred_detect.py

Summary: The list-field merge in the memory layer accepts a bare string
where it expects a list. It then iterates that string with `list()`, which
yields the CHARACTERS of the string. A content-hash dedup step keeps the
first appearance of each character and drops the rest. The order of the
prose goes away, and the number of repeats goes away, so the text cannot be
recovered. This tool reads a store file and reports which records carry
that damage.

WHY THIS TOOL IS SEPARATE FROM THE VECTOR REPAIR, and why the repair cannot
absorb it. The repair compares a stored vector against a recomputed vector.
This damage happens UPSTREAM of that comparison, in the source text. A
faithful encoding of damaged text agrees with itself at each threshold, so
no vector-level check can go red on it. A record damaged at save time
carries a vector that correctly encodes the damage. It does not enter the
repair population at all.

THIS TOOL ANNOTATES. IT DOES NOT FILTER. It emits one annotation per
damaged record and leaves the population alone. A caller that removes these
records from a repair population destroys two things. First, the
pre-registered condition that the repaired subset and the skipped subset
sum to the census. Second, the test of whether a damaged record can reach
the repair population at all, because a filter empties that intersection by
construction and the empty result then reads as a confirmation.

READ-ONLY BY MECHANISM, NOT BY INTENT. The tool opens the file with the
sqlite `mode=ro` and `immutable=1` URI parameters. `immutable=1` tells
sqlite to skip all locking, which is correct ONLY when no writer is active.
So the tool asserts the no-writer precondition in the same call that opens
the file: a `-wal` sidecar or a `-shm` sidecar stops the run. The check and
the open both use one resolved path, so the check cannot bind to a
different spelling of the same file.

THE TOOL IMPORTS NO MODULE FROM THE PACT-MEMORY SCRIPTS PACKAGE. Functions
in that package create the live store directory as a side result of a path
resolution, so an import puts each of them one call away. This rule holds
so that nobody must audit which call is safe. Do not read an absent import
as a guarantee, because a subprocess reaches those functions with no import
at all.

THE TOOL READS THE `memories` TABLE ONLY. That table is an ordinary sqlite
table. The tool names the `vec_memories` virtual table in no query, so it
needs no sqlite extension. A bare sqlite3 cannot load `vec0`.

Usage:
  python3 shred_detect.py <db_path>
  python3 shred_detect.py <db_path> --report out.json
  python3 shred_detect.py <db_path> --quiet --report out.json

Exit codes:
  0  the scan finished. Findings do NOT change this code, because the tool
     annotates and the caller decides.
  2  the no-writer precondition failed, or the file is absent, or the table
     is absent. Nothing was scanned.
<!-- PACT_STORE_BAR_BEGIN -->
**STORE ACCESS.** A memory operation (save, search, get, list, update or
delete a record) goes through the pact-memory CLI. DO NOT USE `--db-path`,
for one verb or for one purpose. YOU DO NOT SELECT A STORE. A path you
choose is not the store the memory of the team lives in, so a save there is
lost rather than shared. STORE INSPECTION is different: a row count, a
column audit, a schema check, or any question about the file itself. To
inspect, do not run a CLI verb, do not import a module below
`skills/pact-memory/scripts/`, and do not open the store read-write. Check
that `memory.db-wal` and `memory.db-shm` are both absent by their full
names, then open the store with `mode=ro` and `immutable=1`. Without
`immutable=1` the open fails. If a sidecar is present, stop and report.
<!-- PACT_STORE_BAR_END -->
The `pact-memory` skill carries the full rule.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# The seven list fields, and how to take ONE text out of one item.
# ---------------------------------------------------------------------------
#
# THE EXTRACTOR IS KEYED BY FIELD. A GENERIC PROBE OVER THE ITEM IS BLIND,
# AND THE BLINDNESS IS STRUCTURAL. Two separate traps make it so.
#
# TRAP 1, the item is not a string. The merge routes each item of a dict
# list field through a dataclass round trip. A bare string becomes the
# primary attribute of that dataclass. So the shredded character "T" is
# stored as {"decision": "T"}, and a healthy item is a dict too. A probe
# that asks "is this item a string of text length 1" answers no for the
# healthy item and no for the damaged item. The two answers agree, so the
# probe cannot separate them at any threshold.
#
# TRAP 2, and this one also defeats a scan over the leaves of the dict. The
# `active_tasks` dataclass ALWAYS emits `status`, whose default value is
# "pending". So a shredded `active_tasks` item is
# {"task": "T", "status": "pending"}, and a probe over the LONGEST string
# leaf reports a text length of 7 and calls the item healthy. Only the
# primary value carries the evidence, so the extractor must know which key
# is primary for each field. That is the reason for the map below.
STRING_LIST_FIELDS: Tuple[str, ...] = (
    "agreements_reached",
    "disagreements_resolved",
    "lessons_learned",
    "reasoning_chains",
)

# field -> the key whose value carries the item text.
DICT_LIST_FIELD_KEYS: Dict[str, str] = {
    "active_tasks": "task",
    "decisions": "decision",
    "entities": "name",
}

LIST_FIELDS: Tuple[str, ...] = tuple(
    sorted(STRING_LIST_FIELDS + tuple(DICT_LIST_FIELD_KEYS))
)

# An item qualifies when its text is this short. Length 0 counts with
# length 1 on purpose. A space in the source prose becomes the empty string,
# because the merge strips each character before it stores it. The empty
# member is therefore evidence of the damage and not a break in it.
MAX_SHRED_ITEM_LEN = 1

# A field fires when this many items qualify. The count is over the WHOLE
# field and not over a consecutive stretch. See the note on the two
# readings below.
MIN_SHRED_ITEMS = 5

# THE FALSE-NEGATIVE BOUND. Print it beside every count. A reader who sees a
# count with no bound reads that count as a census.
FALSE_NEGATIVE_BOUND = (
    "A field needs {min_items} or more qualifying items to fire. A field "
    "shredded from fewer than {min_items} UNIQUE characters escapes this "
    "detector, because the dedup step keeps one item per unique character. "
    "This count is therefore a LOWER BOUND on the damage, and not a census."
).format(min_items=MIN_SHRED_ITEMS)

# THE TWO READINGS OF THE SIGNATURE, AND WHY THE TOOL REPORTS BOTH.
#
# "A run of 5 or more" has two readings. The TOTAL reading counts every
# qualifying item in the field. The CONSECUTIVE reading counts the longest
# unbroken stretch of them. The longest stretch is never larger than the
# total, so the two can disagree in one direction only: the total fires and
# the stretch does not.
#
# THE TOOL FIRES ON THE TOTAL. The reason is the direction of the error.
# The consecutive reading is stricter, so its error is a MISS, and a missed
# record reaches the vector repair, which then writes a correct vector of
# garbage and counts the record repaired. That failure is SILENT. The total
# reading is looser, so its error is an annotation on a healthy record,
# which sends a reader to look. That failure is LOUD. A detector that
# exists to stop a silent miss must not choose the silent error.
#
# THE TOOL REPORTS BOTH NUMBERS ANYWAY, and prints how many rows the two
# readings disagree about. A printed zero is evidence. An assumed zero is a
# check that cannot go red.


class PreconditionError(RuntimeError):
    """The tool refused to open the file. Nothing was read."""


def _resolve(db_path: str) -> Path:
    """Return one absolute, symlink-free path. Use it for every later step."""
    return Path(db_path).expanduser().resolve()


def _sidecars(resolved: Path) -> Tuple[Path, Path]:
    """Return the `-wal` and `-shm` sidecar paths of a resolved store file."""
    return (
        resolved.parent / (resolved.name + "-wal"),
        resolved.parent / (resolved.name + "-shm"),
    )


def open_readonly(db_path: str) -> Tuple[sqlite3.Connection, Path]:
    """
    Assert the no-writer precondition and open the file read-only.

    The assertion and the open live in ONE function on purpose. A caller
    cannot perform the check against one path and the read against another,
    because this function resolves the path one time and uses that result
    for both steps.

    Raise PreconditionError when the file is absent, when a `-wal` sidecar
    is present, or when a `-shm` sidecar is present. A sidecar means a
    writer may hold the file, and `immutable=1` skips locking, so a read
    under a live writer can return a torn view. Stop instead. Do not retry
    in a loop.
    """
    resolved = _resolve(db_path)
    if not resolved.is_file():
        raise PreconditionError("store file is absent: {0}".format(resolved))

    wal, shm = _sidecars(resolved)
    present = [str(p) for p in (wal, shm) if p.exists()]
    if present:
        raise PreconditionError(
            "no-writer precondition FAILED. A writer may hold this store. "
            "Sidecar files present: {0}. Stop and report. Do not retry in a "
            "loop.".format(", ".join(present))
        )

    uri = "{0}?mode=ro&immutable=1".format(resolved.as_uri())
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn, resolved


def item_text(field: str, item: Any) -> Optional[str]:
    """
    Return the ONE text that carries the evidence for this item.

    Return None when the item shape offers no such text. A None result
    means "this item cannot qualify", and the caller counts it as a
    non-qualifying item.
    """
    if field in DICT_LIST_FIELD_KEYS:
        if isinstance(item, dict):
            value = item.get(DICT_LIST_FIELD_KEYS[field])
            return value if isinstance(value, str) else None
        # A legacy row can hold a bare string in a dict field, because the
        # merge keeps an item verbatim when the canonical form raises. Such
        # a string IS the primary value.
        return item if isinstance(item, str) else None
    return item if isinstance(item, str) else None


def scan_field(field: str, items: Sequence[Any]) -> Dict[str, Any]:
    """
    Measure one list field of one record.

    Return the two readings of the signature and the supporting counts.
    `total` counts every qualifying item. `longest_run` counts the longest
    unbroken stretch of qualifying items.
    """
    total = 0
    empty = 0
    longest_run = 0
    run = 0
    for item in items:
        text = item_text(field, item)
        if text is not None and len(text) <= MAX_SHRED_ITEM_LEN:
            total += 1
            run += 1
            if text == "":
                empty += 1
            if run > longest_run:
                longest_run = run
        else:
            run = 0
    return {
        "item_count": len(items),
        "qualifying_total": total,
        "qualifying_longest_run": longest_run,
        "qualifying_empty": empty,
        "fires_on_total": total >= MIN_SHRED_ITEMS,
        "fires_on_longest_run": longest_run >= MIN_SHRED_ITEMS,
    }


def _load_items(raw: Any) -> Tuple[Optional[List[Any]], Optional[str]]:
    """
    Turn one stored column value into a list of items.

    Return (items, None) on success. Return (None, reason) when the value
    cannot become a list. A caller must COUNT the reasons and report them.
    A value skipped without a record is a silent hole in the scan.
    """
    if raw is None:
        return None, "null"
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None, "undecodable_bytes"
    if isinstance(raw, str):
        if raw.strip() == "":
            return None, "empty_text"
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None, "invalid_json"
    else:
        parsed = raw
    if not isinstance(parsed, list):
        return None, "not_a_list"
    return parsed, None


def scan_database(db_path: str) -> Dict[str, Any]:
    """
    Scan one store file and return the report as a plain dictionary.

    The report carries a FINGERPRINT of three values: the store path, the
    row count and the largest `updated_at`. A later tool re-reads those
    three and refuses when they disagree, which makes a stale report
    unusable rather than incorrect without a warning.

    The report also carries the moment of the scan. A count with no date
    becomes a constant in the reader's mind, and this store has produced
    several counts that went stale.
    """
    conn, resolved = open_readonly(db_path)
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        max_updated_at = conn.execute(
            "SELECT MAX(updated_at) FROM memories"
        ).fetchone()[0]

        columns = ", ".join(LIST_FIELDS)
        cursor = conn.execute(
            "SELECT id, project_id, created_at, updated_at, {0} "
            "FROM memories ORDER BY id".format(columns)
        )

        findings: List[Dict[str, Any]] = []
        disagree_ids: List[str] = []
        rows_scanned = 0
        unreadable: Dict[str, int] = {}

        for row in cursor:
            rows_scanned += 1
            annotated: Dict[str, Any] = {}
            row_disagrees = False
            for field in LIST_FIELDS:
                items, reason = _load_items(row[field])
                if items is None:
                    key = "{0}:{1}".format(field, reason)
                    unreadable[key] = unreadable.get(key, 0) + 1
                    continue
                measured = scan_field(field, items)
                if measured["fires_on_total"]:
                    annotated[field] = measured
                    if not measured["fires_on_longest_run"]:
                        row_disagrees = True
            if annotated:
                findings.append({
                    "memory_id": row["id"],
                    "project_id": row["project_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    # THIS FLAG IS ONE-DIRECTIONAL. READ THE NAME LITERALLY.
                    # True means no update has touched the record since it
                    # was created, so the damage dates from the create
                    # step. False means ONLY that some update touched the
                    # record, because an update to ANY field stamps
                    # `updated_at`. False does NOT name the step that
                    # caused the damage. A record damaged at create and
                    # updated later on a different field reads False.
                    "never_updated_since_create": (
                        row["created_at"] == row["updated_at"]
                    ),
                    "fields": annotated,
                })
                if row_disagrees:
                    disagree_ids.append(row["id"])
    finally:
        conn.close()

    return {
        "tool": "shred_detect",
        "report_version": 1,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": {
            "db_path": str(resolved),
            "row_count": row_count,
            "max_updated_at": max_updated_at,
        },
        "signature": {
            "fires_on": "qualifying_total",
            "min_items": MIN_SHRED_ITEMS,
            "max_item_text_len": MAX_SHRED_ITEM_LEN,
            "false_negative_bound": FALSE_NEGATIVE_BOUND,
        },
        "fields_scanned": list(LIST_FIELDS),
        "findings": findings,
        "summary": {
            "rows_scanned": rows_scanned,
            "rows_annotated": len(findings),
            "reading_disagreement_rows": len(disagree_ids),
            "reading_disagreement_ids": disagree_ids,
            "unreadable_field_values": unreadable,
            "row_count_agrees_with_scan": row_count == rows_scanned,
        },
    }


def render_text(report: Dict[str, Any]) -> str:
    """Render the report for a human reader. Keep the bound beside the count."""
    summary = report["summary"]
    fingerprint = report["fingerprint"]
    lines = [
        "shred_detect report",
        "  store            : {0}".format(fingerprint["db_path"]),
        "  scanned at       : {0}".format(report["scanned_at"]),
        "  rows in table    : {0}".format(fingerprint["row_count"]),
        "  rows scanned     : {0}".format(summary["rows_scanned"]),
        "  max(updated_at)  : {0}".format(fingerprint["max_updated_at"]),
        "",
        "  rows annotated   : {0}".format(summary["rows_annotated"]),
        "  BOUND            : {0}".format(report["signature"]["false_negative_bound"]),
        "",
        # PRINT THIS NUMBER ALWAYS, INCLUDING WHEN IT IS ZERO. A printed
        # zero is evidence that the two readings were both computed and
        # compared. An absent line leaves a reader unable to tell a
        # measured agreement from a check that never ran.
        "  rows where the TOTAL reading and the CONSECUTIVE reading "
        "disagree: {0}".format(summary["reading_disagreement_rows"]),
    ]
    if summary["reading_disagreement_ids"]:
        lines.append(
            "    ids: {0}".format(", ".join(summary["reading_disagreement_ids"]))
        )
    if summary["unreadable_field_values"]:
        lines.append("  field values that could not become a list:")
        for key in sorted(summary["unreadable_field_values"]):
            lines.append(
                "    {0}: {1}".format(key, summary["unreadable_field_values"][key])
            )
    if not summary["row_count_agrees_with_scan"]:
        lines.append(
            "  WARNING: the row count and the scanned count disagree. "
            "Treat this report as unsound."
        )
    lines.append("")
    for finding in report["findings"]:
        lines.append("  {0}  project={1}".format(
            finding["memory_id"], finding["project_id"]
        ))
        for name in sorted(finding["fields"]):
            measured = finding["fields"][name]
            lines.append(
                "      {0}: total={1} longest_run={2} empty={3} of {4} items"
                .format(
                    name,
                    measured["qualifying_total"],
                    measured["qualifying_longest_run"],
                    measured["qualifying_empty"],
                    measured["item_count"],
                )
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shred_detect",
        description=(
            "Report memory records whose list fields hold shredded prose. "
            "Read-only. This tool annotates and does not filter."
        ),
    )
    parser.add_argument("db_path", help="path to the store file to scan")
    parser.add_argument(
        "--report",
        default=None,
        help="write the JSON report to this path. It must not be inside the store directory.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="do not render the human-readable report on stdout",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = scan_database(args.db_path)
    except PreconditionError as exc:
        print("shred_detect REFUSED: {0}".format(exc), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print("shred_detect could not read the store: {0}".format(exc), file=sys.stderr)
        return 2

    if args.report:
        out = Path(args.report).expanduser().resolve()
        store_dir = Path(report["fingerprint"]["db_path"]).parent
        if out.parent == store_dir:
            print(
                "shred_detect REFUSED to write the report into the store "
                "directory: {0}".format(out),
                file=sys.stderr,
            )
            return 2
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if not args.quiet:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
