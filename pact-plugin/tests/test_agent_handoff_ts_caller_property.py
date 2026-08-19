"""The `agent_handoff` ordering rule rests on a CALLER property. Enforce it.

WHAT RESTS ON THIS. The harvest resolves a multi-event `agent_handoff` group
by taking the latest `ts`, and `session_resume` does the same when it renders
its Completed Work summary. Both compare `ts` AS A STRING. A string compare
orders timestamps correctly only while every event of the family carries ONE
format.

WHY THAT IS A CALLER PROPERTY AND NOT A SCHEMA PROPERTY, WHICH IS THE WHOLE
CAUSE FOR THIS FILE. `session_journal.make_event` stamps its own timestamp
through `setdefault("ts", ...)`, so A CALLER-SUPPLIED `ts` IS PRESERVED. The
schema does not reject one and nothing warns. The one-format property
thus belongs to the CALLERS, and it holds today only because neither
`agent_handoff` emit path passes a `ts` of its own.

THE FAILURE IS SILENT AND IT RUNS IN EITHER DIRECTION. `make_event` stamps a
Z-suffix form and `canonical_since()` emits an offset form. MEASURED:
`ord('+')` is 43 and `ord('Z')` is 90, so for two spellings of ONE instant
the offset form sorts as OLDER. AND THE COMMON SHORT FORM OF THIS HAZARD,
that an offset form always sorts as older, IS TOO STRONG: a string compare
walks left to right, so the DATETIME PREFIX decides first and the suffix
decides nothing until every byte before it is equal. A non-UTC offset naming
the same instant carries a different hour and sorts as NEWER. The accurate
statement is that a mixed-format set is ordered BY BYTES AND NOT BY TIME.
Either way the latest-wins rule can keep the incorrect event, and no test in
the family reddens.

WHAT THIS FILE DOES AND DOES NOT DO. It converts correct-by-a-caller-property
into the caller property ENFORCED: a future edit that passes a `ts` to either
emit path turns this RED at the moment it is written. It does NOT make the
comparison safe against a mixed set, and it is not a substitute for the prose
in the harvest skill that tells a reader to parse the two forms before
comparing them if a caller ever does pass one. The prose reaches the person
who would make that change. This file catches them if the prose does not.
"""

import ast
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

# The two agent_handoff emit paths. Named rather than derived: this is a
# claim ABOUT these two files, so discovering them from the property this file
# tests would make the assertion agree with whatever it found.
EMIT_PATHS = (
    _HOOKS_DIR / "agent_handoff_emitter.py",
    _HOOKS_DIR / "task_lifecycle_gate.py",
)

EVENT_TYPE = "agent_handoff"


def _agent_handoff_make_event_calls(source_path: Path) -> list:
    """Every `make_event("agent_handoff", ...)` call in one module."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "make_event":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value == EVENT_TYPE:
            calls.append(node)
    return calls


class TestNeitherEmitPathSuppliesATimestamp:
    """The caller property the string compare rests on."""

    @pytest.mark.parametrize("source_path", EMIT_PATHS, ids=lambda p: p.name)
    def test_no_agent_handoff_emit_passes_ts(self, source_path):
        calls = _agent_handoff_make_event_calls(source_path)
        for call in calls:
            keywords = sorted(k.arg for k in call.keywords if k.arg)
            assert "ts" not in keywords, (
                f"{source_path.name} passes `ts` to make_event for an "
                f"{EVENT_TYPE} event. make_event uses setdefault, so that "
                f"value is PRESERVED, and a second timestamp format breaks "
                f"the string compare the latest-wins rule uses. A mixed "
                f"set then orders BY BYTES and not by time, in either "
                f"direction, and the newest write can lose in silence. "
                f"Keywords found: {keywords}"
            )

    def test_the_population_this_arm_scans_is_not_empty(self):
        """🔴 A 'none of them passes ts' ASSERTION PASSES FOR FREE ON ZERO
        CALLS, so the population is pinned here.

        A rename of `make_event`, a move of either emit site, or a change to
        the event-type literal would empty the scan, and the arm above would
        report green about a set it could not find. This arm fails,
        and it names the count so a THIRD emit path arriving is visible too.
        """
        found = {
            path.name: len(_agent_handoff_make_event_calls(path))
            for path in EMIT_PATHS
        }
        assert all(count >= 1 for count in found.values()), (
            f"an emit path carries NO {EVENT_TYPE} make_event call, so the "
            f"arm above scanned nothing and passed for free. Counts: {found}"
        )
        assert sum(found.values()) == 2, (
            f"the {EVENT_TYPE} emit population is not two calls at this time. A "
            f"third emit path must be added to EMIT_PATHS and to the prose "
            f"that names the two. Counts: {found}"
        )


class TestTheInstrumentAndThePremise:
    """The two facts the arms above rest on, each shown able to fail."""

    def test_make_event_preserves_a_caller_supplied_ts(self):
        """The premise. If make_event ever OVERWROTE `ts`, the property
        above would stop mattering and this file could retire."""
        from shared.session_journal import make_event

        supplied = "2020-01-01T00:00:00+00:00"
        event = make_event(EVENT_TYPE, ts=supplied)
        assert event["ts"] == supplied, (
            "make_event does not preserve a caller ts at this time. The caller "
            "property this file enforces is not load-bearing at this time, and "
            "this file and the prose adjacent to the ordering helper want a "
            "re-read together."
        )

    def test_a_mixed_format_set_orders_by_bytes_and_not_by_time(self):
        """The consequence, held as an executable fact rather than prose.

        🔴 AND THE BOUND IS TIGHTER THAN "AN OFFSET FORM SORTS AS OLDER",
        WHICH IS THE FORM THIS HAZARD IS USUALLY STATED IN. MEASURED while
        writing this arm, because the first draft of it FAILED: the suffix
        decides nothing until every byte before it is equal. A string
        compare walks left to right, so the DATETIME PREFIX dominates, and
        `2026-08-19T21:00:00+00:00` sorts AFTER `2026-08-19T20:00:00Z` on
        the hour, not before it on the suffix.

        THE ACCURATE STATEMENT IS THAT A MIXED-FORMAT SET IS ORDERED BY
        BYTES AND NOT BY TIME, and the error runs in EITHER direction:
          - equal prefix, two spellings of ONE instant: `+` at 43 sorts
            before `Z` at 90, so the offset form reads as OLDER.
          - a non-UTC offset naming the SAME instant carries a DIFFERENT
            hour, so it reads as NEWER.
        Both are incorrect and neither raises.
        """
        # Case one: one instant, two spellings, equal prefix.
        z_form = "2026-08-19T20:00:00Z"
        same_instant_offset = "2026-08-19T20:00:00+00:00"
        assert same_instant_offset < z_form, (
            "the offset spelling does not sort before the Z spelling at this time, for "
            "one instant. The inversion this file guards has changed shape."
        )
        # Case two: one instant, a non-UTC offset, so a different prefix.
        later_looking_offset = "2026-08-19T21:00:00+01:00"
        assert later_looking_offset > z_form, (
            "a non-UTC offset naming the same instant does not sort "
            "after the Z form. The second direction of the error is gone."
        )

    def test_the_scan_ignores_a_different_event_type(self):
        """The instrument must select on the event type, or it would report
        about calls this claim does not cover."""
        source = (
            "make_event('dispatch_variety', ts='x')\n"
            "make_event('agent_handoff', agent='a')\n"
        )
        tree = ast.parse(source)
        selected = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "make_event"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == EVENT_TYPE
        ]
        assert len(selected) == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
