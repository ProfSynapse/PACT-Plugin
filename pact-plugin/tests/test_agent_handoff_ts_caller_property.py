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
comparison safe against a mixed set.

🔴 THE LOAD-BEARING ASSERTION IN THIS FILE IS THE CALLER-PROPERTY ARM, AND
THE BYTE-RULE ARM IS AN EXPLANATION OF WHAT IS LOST IF THAT PROPERTY GOES.
Read them in that order. If a caller ever does pass a `ts`, the answer is to
PARSE the two values, not to reach for a rule about which byte decides. That
instruction is the one part of this warning that has needed no correction
across three rounds of review: a claim, then a rule replacing the claim, then
a precondition replacing the rule, each complete across its own list of
spellings and each broken by the next probe.
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

    def test_the_first_byte_after_the_seconds_decides_the_order(self):
        """THE RULE, ASSERTED AS A RULE AND NOT AS A LIST OF PAIRS.

        A list of spellings keeps growing, and an arm that pins five pairs
        goes stale the moment a sixth spelling arrives while reporting
        green. So this asserts the ORDERING FUNCTION: at ONE datetime
        prefix, the string order of the stamps equals the order of the
        FIRST BYTE AFTER THE SECONDS.

        WHY THE RULE IS STATED AT THAT BYTE AND CONDITIONED ON AN EQUAL
        PREFIX. A string compare walks left to right, so the datetime
        prefix decides first and the suffix byte is reached only when each
        byte before it agrees. An earlier form of this record said an
        offset form sorts as OLDER, without that condition, and it came
        from a probe that compared ONE CHARACTER and no pair of stamps at
        all. A single-byte fact cannot carry a claim about a whole-string
        compare.

        A missing suffix takes the key -1, because a shorter string that is
        a prefix of a longer one sorts first.

        🔴 THE PRECONDITION, AND THE RULE IS INCORRECT OUTSIDE IT: THE
        DATETIME PREFIX MUST BE FIXED-WIDTH AND THE SECONDS MUST BE PRESENT.
        MEASURED, two forms that break it, and neither is chased into the
        fixture above because adding them is the enumeration returning by
        another route:
          - `2026-08-19 20:00:00+00:00` decides at INDEX 10, a SPACE at 0x20
            against `T` at 0x54, which is nine bytes before the position this
            rule names. `str(datetime.now(timezone.utc))` produces it.
          - `2026-08-19T20:00:00.123Z` against `2026-08-19T20:00:00.123456Z`
            carries `.` as the byte after the seconds for BOTH, so the rule
            answers NOTHING. The compare decides at INDEX 23, and the LATER
            instant reads as older. Two ordinary calls in one codebase make
            that pair.
        A `timespec='minutes'` form has no seconds field, so the named
        position does not exist at all.

        THE BOUND: that list comes from a probe of the stdlib producers and
        one hand-built form. A producer outside those is outside the check,
        and NO RULE ABOUT WHICH BYTE DECIDES CAN BE MADE COMPLETE, because a
        new spelling can move the deciding byte somewhere no rule anticipated.
        THAT is why the parse instruction outranks this arm.
        """
        prefix = "2026-08-19T20:00:00"
        # DELIBERATELY NOT IN BYTE ORDER. The guard at the end of this
        # arm asserts the sort did work, and a fixture that is in byte
        # order from the start makes the agreement free. My first draft of
        # this tuple was in byte order and that guard caught it.
        spellings = ("Z", "z", "", ".123456Z", "-05:00", "+00:00")

        def first_suffix_byte(suffix: str) -> int:
            return ord(suffix[0]) if suffix else -1

        by_string = sorted(spellings, key=lambda suffix: prefix + suffix)
        by_byte = sorted(spellings, key=first_suffix_byte)
        assert by_string == by_byte, (
            f"the string order and the first-suffix-byte order disagree, so "
            f"the rule this file records is incorrect. By string: "
            f"{by_string}. By byte: {by_byte}."
        )
        # The rule has content only if the two orders are not the input
        # order by accident. This pins that the set is genuinely reordered.
        assert by_string != list(spellings), (
            "the fixture set arrived in byte order, so the agreement "
            "above is free and this arm measures nothing."
        )

    def test_a_fraction_makes_the_later_instant_read_as_older(self):
        """The most reachable case, kept as an illustration of the rule.

        A bare `datetime.now(timezone.utc).isoformat()` emits MICROSECONDS
        by default, so a caller reaches this by writing the obvious thing.
        An offset takes a deliberate choice.
        """
        z_form = "2026-08-19T20:00:00Z"
        later_instant_with_fraction = "2026-08-19T20:00:00.123456Z"
        assert later_instant_with_fraction < z_form, (
            "a fractional-second stamp does not sort before the Z form at "
            "this time. `.` at 0x2E sorts before `Z` at 0x5A, so the LATER "
            "instant reads as the older one and latest-wins keeps the "
            "wrong event."
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
