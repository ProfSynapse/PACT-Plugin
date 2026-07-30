"""
Location: pact-plugin/tests/test_pin_caps_boundedness.py
Summary: Verification tests for the pinned-region boundedness contract --
         `staleness.PinnedSection.bounded` and the tree-wide guard that no
         consumer reads a `_parse_pinned_section` result by integer index.
Used by: the pytest suite. Companion to hooks/staleness.py (the parser),
         hooks/pin_caps.py and hooks/pin_caps_gate.py (the consumers).

These are CODE-phase verification tests, not the full behavioural matrix.
They pin two properties that a green suite cannot otherwise observe.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from shared.claude_md_manager import (  # noqa: E402
    MANAGED_END_MARKER,
    MANAGED_START_MARKER,
    extract_managed_region,
    match_project_claude_md,
)
from staleness import _parse_pinned_section  # noqa: E402

# Repository root that the tree-wide guard walks. Parent of `pact-plugin`.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _managed(body: str) -> str:
    """Wrap `body` in the REAL managed markers.

    Never hand-spell a marker in a fixture. `extract_managed_region` matches
    the full literal, so a shortened spelling makes it return None, the
    parser falls back to scanning the whole file, and every boundedness
    assertion below silently collapses onto the agreeing branch.
    """
    return f"{MANAGED_START_MARKER}\n{body}{MANAGED_END_MARKER}\n"


_PINS = (
    "## Pinned Context\n"
    "<!-- pinned: 2026-01-01 -->\n"
    "### Real pin\n"
    "Pin body.\n"
    "\n"
    "### 2026-07-30\n"
    "An ordinary Working Memory note.\n"
)

# Same pins, plus the terminator heading that closes the section.
UNBOUNDED_FIXTURE = _managed(_PINS)
BOUNDED_FIXTURE = _managed(_PINS + "\n## Working Memory\n- entry\n")


class TestPinnedSectionBounded:
    """`bounded` must discriminate, and must use the SCAN-RELATIVE formula."""

    @pytest.mark.parametrize(
        "fixture", [UNBOUNDED_FIXTURE, BOUNDED_FIXTURE]
    )
    def test_fixture_is_actually_managed(self, fixture):
        """Per-fixture managed-state control.

        MANDATORY, and it is not ceremony. On a file with no managed
        markers the scan text IS the full content, so the correct and the
        incorrect boundedness formulas coincide. A fixture that lost its
        markers therefore passes every assertion below while measuring
        nothing.
        """
        assert extract_managed_region(fixture) is not None

    def test_unbounded_region_reports_not_bounded(self):
        parsed = _parse_pinned_section(UNBOUNDED_FIXTURE)
        assert parsed is not None
        assert parsed.bounded is False

    def test_bounded_region_reports_bounded(self):
        parsed = _parse_pinned_section(BOUNDED_FIXTURE)
        assert parsed is not None
        assert parsed.bounded is True

    def test_the_two_arms_disagree(self):
        """Anti-vacuity control.

        The two fixtures differ in ONE property: whether a `## Working
        Memory` heading follows the pins. If both arms read the same, the
        pair is one arm twice and the tests above certify nothing.
        """
        unbounded = _parse_pinned_section(UNBOUNDED_FIXTURE)
        bounded = _parse_pinned_section(BOUNDED_FIXTURE)
        assert unbounded is not None and bounded is not None
        assert unbounded.bounded != bounded.bounded

    def test_full_file_formula_would_disagree_on_a_marked_file(self):
        """Pin the FORMULA, not only its result on this fixture.

        `bounded` MUST come from the scan-relative locals
        (`pinned_end < len(scan_text)`), computed before the managed-region
        offset is added. The full-file form (`end < len(content)`) is the
        one a reader naturally reaches for at the return statement, because
        the offsets in hand there are already absolute.

        On any MARKED file the full-file form is unconditionally True: the
        scanned text is sliced to stop BEFORE `PACT_MANAGED_END`, so the
        closing marker always follows it. This asserts the two forms
        DIVERGE here and that `bounded` took the correct one. Swap the
        implementation to the full-file form and this test reddens.
        """
        parsed = _parse_pinned_section(UNBOUNDED_FIXTURE)
        assert parsed is not None
        assert parsed.end < len(UNBOUNDED_FIXTURE), (
            "precondition: the full-file form must read True here, "
            "otherwise this test cannot discriminate the two formulas"
        )
        assert parsed.bounded is False, (
            "bounded was computed from the full-file offsets. Use the "
            "scan-relative locals: pinned_end < len(scan_text)."
        )


# ---------------------------------------------------------------------------
# Tree-wide guard: no integer-index read of a _parse_pinned_section result.
#
# WHY THIS IS TEXTUAL AND NOT BEHAVIOURAL. A three-name positional unpack of
# the four-field NamedTuple raises ValueError, so those consumers announce
# themselves. An INDEX read does not: `parsed[2]` and `parsed.content` return
# the identical object on a NamedTuple, so a site left un-migrated keeps
# working and the suite stays green. A behavioural check cannot see it, which
# is exactly what "survives silently" means.
# ---------------------------------------------------------------------------

_PARSER_NAME = "_parse_pinned_section"


_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)


def _walk_scope(scope: ast.AST):
    """Yield every descendant of `scope` WITHOUT entering a nested scope.

    Scoping is load-bearing here, not tidiness. A module-wide analysis binds
    a variable name in one function and then reports a same-named variable
    in another. This detector caught exactly that on its first run: a
    `parsed` bound from `parse_pins` in one test was reported against a
    `parsed` bound from `_parse_pinned_section` in a different helper. The
    finding was real detection with false attribution, which is a wrong
    answer and not a gap.
    """
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, _SCOPE_NODES):
            continue
        yield child
        yield from _walk_scope(child)


def _index_reads_in_one_scope(scope: ast.AST) -> list[tuple[str, int]]:
    """Bind and report within a SINGLE scope. See `_walk_scope`."""
    bound: set[str] = set()
    for node in _walk_scope(scope):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        called = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else ""
        )
        if called != _PARSER_NAME:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                bound.add(target.id)

    if not bound:
        return []

    findings: list[tuple[str, int]] = []
    for node in _walk_scope(scope):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if not isinstance(value, ast.Name) or value.id not in bound:
            continue
        index = node.slice
        if isinstance(index, ast.Constant) and isinstance(index.value, int):
            findings.append((value.id, node.lineno))
    return findings


def _index_reads_of_parser_result(source: str) -> list[tuple[str, int]]:
    """Return (variable, lineno) for every integer-index read of a parser result.

    Finds names bound from a `_parse_pinned_section(...)` call (in any
    spelling: bare, `staleness._parse_pinned_section`, or a module alias),
    then reports any `name[<int>]` subscript on one of those names IN THE
    SAME SCOPE.
    """
    tree = ast.parse(source)
    scopes = [tree] + [
        node for node in ast.walk(tree) if isinstance(node, _SCOPE_NODES[:3])
    ]
    findings: list[tuple[str, int]] = []
    for scope in scopes:
        findings.extend(_index_reads_in_one_scope(scope))
    return sorted(findings, key=lambda item: item[1])


def _python_sources() -> list[Path]:
    return [
        path
        for path in _PLUGIN_ROOT.rglob("*.py")
        if ".git" not in path.parts
    ]


class TestNoPositionalIndexReadOfParserResult:

    def test_detector_fires_on_a_known_violation(self):
        """Positive control for the detector itself.

        A tree scan that reports zero findings is indistinguishable from a
        scan whose detector is broken. Feed it the exact shape the two
        migrated sites used and require a hit.
        """
        violation = (
            "def helper(content):\n"
            "    parsed = _parse_pinned_section(content)\n"
            "    return parsed[2]\n"
        )
        assert _index_reads_of_parser_result(violation) == [("parsed", 3)]

    def test_detector_accepts_the_migrated_shape(self):
        """Counter-control: the correct shape must NOT be reported."""
        migrated = (
            "def helper(content):\n"
            "    parsed = _parse_pinned_section(content)\n"
            "    return parsed.content\n"
        )
        assert _index_reads_of_parser_result(migrated) == []

    def test_detector_does_not_bind_across_scopes(self):
        """The detector must not report a same-named variable in ANOTHER
        function that was bound from a different call.

        This is the false positive the first run produced. Without
        per-scope binding the module-level `parsed` from the parser leaks
        onto an unrelated `parsed` from `parse_pins`, and the guard
        reports a site that is correct.
        """
        two_scopes = (
            "def uses_the_parser(content):\n"
            "    parsed = _parse_pinned_section(content)\n"
            "    return parsed.content\n"
            "\n"
            "def uses_something_else(source):\n"
            "    parsed = parse_pins(source)\n"
            "    return parsed[0]\n"
        )
        assert _index_reads_of_parser_result(two_scopes) == []

    def test_scan_reaches_the_files_that_call_the_parser(self):
        """Non-empty-input control for the tree walk.

        Without this, an empty rglob, a wrong root, or a rename of the
        parser would produce a green "no findings" that means nothing.
        """
        callers = [
            path for path in _python_sources()
            if f"{_PARSER_NAME}(" in path.read_text(encoding="utf-8")
        ]
        assert len(callers) >= 7, (
            f"expected the parser's call sites to be reachable from "
            f"{_PLUGIN_ROOT}, found {len(callers)}"
        )

    def test_no_index_read_survives_anywhere_in_the_tree(self):
        findings: list[str] = []
        for path in _python_sources():
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if f"{_PARSER_NAME}" not in source:
                continue
            try:
                hits = _index_reads_of_parser_result(source)
            except SyntaxError:
                continue
            findings.extend(
                f"{path}:{lineno}: {name}[...]" for name, lineno in hits
            )
        assert findings == [], (
            "integer-index read of a _parse_pinned_section result. It "
            "returns a PinnedSection; read it by field name. An index read "
            "keeps working after the shape change and reports nothing:\n"
            + "\n".join(findings)
        )


# ---------------------------------------------------------------------------
# The boundedness DECLINE at the gate.
#
# READ THE VACUITY HAZARD FIRST, because it decides the whole design below.
#
# The natural fixture pair for this fix is "the same good-faith action on an
# unbounded file and on a bounded file". That pair DEMONSTRATED the defect,
# and it is useless for certifying the FIX: before the fix the arms read DENY
# and ALLOW, after the fix they read ALLOW and ALLOW. A pair that agrees is
# one arm twice, so a gate that had been deleted outright would pass it.
#
# So the arms below discriminate on a property the fix does NOT erase:
#
#   ALLOW arm   unbounded region, 14 PHANTOM pins  -> allow, and the decline
#               classification proves WHICH branch produced the allow.
#   DENY arm    bounded region, 13 REAL pins       -> still denies.
#
# Both arms are "over the count cap" by measurement. They differ only in
# whether the measurement can be trusted, which is exactly what the gate now
# tests. An implementation that declines unconditionally reddens the DENY
# arm; one that never declines reddens the ALLOW arm.
# ---------------------------------------------------------------------------

_REAL_PIN = "<!-- pinned: 2026-07-30 -->\n### Real pin {n}\nShort body.\n\n"
_NOTE = "### 2026-07-{d:02d}\n**Context**: routine session note.\n\n"

_TERMINATOR = "## Working Memory\n\n"


def _claude_md(*, real_pins: int, notes: int, bounded: bool) -> str:
    """Build a CLAUDE.md from the REAL marker constants.

    Never hand-spell a marker here. `extract_managed_region` matches the
    full literal; a short spelling returns None, the parser silently falls
    back to the whole file, and every arm collapses onto the branch where
    the correct and incorrect behaviours agree.

    `bounded` inserts the terminating H2 BETWEEN the dated pins and the
    undated notes. That position is the whole point: a terminator placed
    after the notes bounds the region at the end it already had and leaves
    the notes inside it, which is the same phantom count with `bounded`
    reading True.
    """
    body = "".join(_REAL_PIN.format(n=i) for i in range(1, real_pins + 1))
    if bounded:
        body += _TERMINATOR
    body += "".join(_NOTE.format(d=d) for d in range(1, notes + 1))
    return (
        "# PACT Framework and Managed Project Memory\n\n"
        f"{MANAGED_START_MARKER}\n"
        "## Pinned Context\n\n"
        f"{body}"
        f"{MANAGED_END_MARKER}\n"
    )


@pytest.fixture
def gate_env(tmp_path, monkeypatch, pact_context):
    """A gate harness whose CLAUDE.md is the one in `tmp_path`.

    Captures `append_failure` so a decline is observable by a POSITIVE
    value (its classification) rather than by an absence.
    """
    claude_md = tmp_path / "CLAUDE.md"
    pact_context(
        team_name="test-team",
        session_id="session-boundedness",
        project_dir=str(tmp_path),
    )

    import staleness
    monkeypatch.setattr(
        staleness, "get_project_claude_md_path", lambda: claude_md
    )

    failures: list[dict] = []

    import pin_caps_gate
    monkeypatch.setattr(
        pin_caps_gate,
        "append_failure",
        lambda classification, error=None, cwd=None, source=None: failures.append(
            {"classification": classification, "source": source}
        ),
    )
    return {"claude_md": claude_md, "failures": failures, "tmp_path": tmp_path}


def _verdict(env, content: str, tool_input: dict):
    """Run the gate and return (deny_reason, failures).

    THE BINDING CONTROL LIVES HERE, NOT IN A TEST OF ITS OWN, and that
    placement is deliberate. `_check_tool_allowed` short-circuits to ALLOW
    when the target does not resolve to the canonical project CLAUDE.md. A
    harness whose path resolution escapes the temp directory therefore
    reports ALLOW on EVERY arm — a clean, believable, and entirely false
    result, which is how a first run of this exact measurement once
    concluded "no defect here".

    A control in a sibling test cannot prevent that: it passes while the
    other tests report their false verdicts. So the precondition is
    asserted on the path that PRODUCES the verdict, and a failure here
    WITHHOLDS the verdict rather than annotating it.
    """
    env["claude_md"].write_text(content, encoding="utf-8")

    canonical = match_project_claude_md(str(env["claude_md"]))
    assert canonical is not None, (
        "BINDING CONTROL FAILED: the gate would short-circuit before "
        "reaching the arm under test, and every verdict below would read "
        "ALLOW for a reason that has nothing to do with boundedness."
    )
    assert env["tmp_path"] in canonical.parents, (
        f"BINDING CONTROL FAILED: canonical CLAUDE.md resolved to "
        f"{canonical}, outside the temp directory. The harness is "
        f"measuring the real repository file."
    )

    from pin_caps_gate import _check_tool_allowed
    env["failures"].clear()
    reason = _check_tool_allowed({
        "tool_name": "Edit",
        "agent_type": "pact-orchestrator",
        "tool_input": {"file_path": str(env["claude_md"]), **tool_input},
    })
    return reason, list(env["failures"])


# A legitimate, dated pin add. The action is identical in both arms.
_ADD_A_PIN = {
    "old_string": "### Real pin 1\nShort body.\n",
    "new_string": (
        "### Real pin 1\nShort body.\n\n"
        "<!-- pinned: 2026-07-31 -->\n### Real pin new\nShort body.\n"
    ),
    "replace_all": False,
}


class TestBoundednessDecline:

    def test_unbounded_phantom_over_cap_is_allowed(self, gate_env):
        """The over-block fix. 2 real pins measured as 14 must NOT deny."""
        content = _claude_md(real_pins=2, notes=12, bounded=False)
        reason, failures = _verdict(gate_env, content, _ADD_A_PIN)
        assert reason is None, (
            f"cardinal over-block: a curator with 2 real pins was denied "
            f"with {reason!r}"
        )
        assert [f["classification"] for f in failures] == [
            "pin_caps_gate_declined_unbounded_both"
        ], (
            "the allow must come from the boundedness decline. Without this "
            "the arm cannot tell 'declined' from 'evaluated and found clean', "
            "and a deleted gate would pass."
        )

    def test_bounded_genuine_over_cap_still_denies(self, gate_env):
        """Enforcement survives. 13 REAL pins on a bounded region deny."""
        content = _claude_md(real_pins=13, notes=0, bounded=True)
        reason, failures = _verdict(gate_env, content, _ADD_A_PIN)
        assert reason is not None, (
            "the gate stopped enforcing on a trustworthy measurement. A "
            "decline on every input passes the allow arm and is wrong."
        )
        assert "cap" in reason.lower()
        assert failures == [], (
            "the ENFORCED path must write no failure_log entry: the log is "
            "a bounded ring buffer and a per-call entry evicts real faults."
        )

    def test_the_two_arms_disagree(self, gate_env):
        """Mandatory anti-vacuity control.

        Both arms are over the count cap by measurement. If they read the
        same verdict, the pair certifies nothing.
        """
        allow_reason, _ = _verdict(
            gate_env, _claude_md(real_pins=2, notes=12, bounded=False),
            _ADD_A_PIN,
        )
        deny_reason, _ = _verdict(
            gate_env, _claude_md(real_pins=13, notes=0, bounded=True),
            _ADD_A_PIN,
        )
        assert (allow_reason is None) != (deny_reason is None)

    def test_ordinary_note_on_unbounded_region_is_allowed(self, gate_env):
        """PRECEDENCE. This is the arm that catches a decline placed too low.

        Appending an ordinary undated Working Memory note is the most
        common action a curator takes. On an unbounded region that note
        matches the embedded-pin smuggle signature, and the embedded-pin
        test fires INSIDE `compute_deny_reason`, BEFORE either cap axis.

        So a decline placed after the `compute_deny_reason` call leaves
        this arm denying while the count and size arms are fixed. Move the
        decline below that call and this test reddens; the two cap arms
        above do not.
        """
        content = _claude_md(real_pins=2, notes=12, bounded=False)
        add_note = {
            "old_string": "### 2026-07-12\n**Context**: routine session note.\n",
            "new_string": (
                "### 2026-07-12\n**Context**: routine session note.\n\n"
                "### 2026-07-31\n**Context**: today's note.\n"
            ),
            "replace_all": False,
        }
        assert add_note["old_string"] in content, "fixture anchor not present"
        reason, failures = _verdict(gate_env, content, add_note)
        assert reason is None, (
            f"cardinal over-block on the most ordinary action there is. "
            f"The decline is placed after compute_deny_reason. Got {reason!r}"
        )
        assert failures and failures[0]["classification"].startswith(
            "pin_caps_gate_declined_unbounded"
        )

    def test_repair_edit_is_allowed_and_classified_pre(self, gate_env):
        """The curator repairs the file by hand: pre unbounded, post bounded.

        The gate MUST allow it, and the classification must say `_pre` —
        the state the operator most needs to tell apart, because it is the
        one where the file is getting BETTER.
        """
        content = _claude_md(real_pins=2, notes=12, bounded=False)
        repair = {
            "old_string": "### 2026-07-01\n",
            "new_string": "## Working Memory\n\n### 2026-07-01\n",
            "replace_all": False,
        }
        assert repair["old_string"] in content, "fixture anchor not present"
        reason, failures = _verdict(gate_env, content, repair)
        assert reason is None
        assert [f["classification"] for f in failures] == [
            "pin_caps_gate_declined_unbounded_pre"
        ]


class TestDeclineClassification:
    """The mapping is total, and every value it returns is true of its input."""

    def test_each_declining_pair_maps_to_its_own_value(self):
        from pin_caps_gate import _decline_classification

        assert _decline_classification(False, False).endswith("_both")
        assert _decline_classification(True, False).endswith("_post")
        assert _decline_classification(False, True).endswith("_pre")

    def test_the_three_values_are_distinct(self):
        """Anti-vacuity: three names that resolve to one string certify nothing."""
        from pin_caps_gate import _decline_classification

        values = {
            _decline_classification(False, False),
            _decline_classification(True, False),
            _decline_classification(False, True),
        }
        assert len(values) == 3

    def test_no_value_collides_with_a_gate_fault_code(self):
        """A decline is NOT a gate fault and must not land in that population."""
        import pin_caps_gate

        fault_codes = {
            getattr(pin_caps_gate, name)
            for name in dir(pin_caps_gate)
            if name.startswith("_FAIL_")
        }
        assert fault_codes, "control: the fault codes must be discoverable"
        declines = {
            pin_caps_gate._DECLINED_UNBOUNDED_BOTH,
            pin_caps_gate._DECLINED_UNBOUNDED_POST,
            pin_caps_gate._DECLINED_UNBOUNDED_PRE,
        }
        assert declines.isdisjoint(fault_codes)

    def test_both_bounded_is_not_a_decline(self):
        """Pin the unreachable default so it cannot become a silent wrong code.

        Both-bounded does not decline, so it has no true classification.
        The caller tests boundedness before calling, so this input does not
        occur on the gate path. This test exists so that a future caller who
        DOES route a bounded pair here meets a documented expectation rather
        than a plausible-looking `_pre` entry in the operator's log.
        """
        from pin_caps_gate import _DECLINED_UNBOUNDED_BOTH, _decline_classification

        assert _decline_classification(True, True) == _DECLINED_UNBOUNDED_BOTH


class TestRegionStateContract:

    def test_bounded_is_copied_from_the_parser_not_recomputed(self):
        """One definition of boundedness. Two would drift.

        Asserts the value the gate carries is the value the parser
        produced, on both arms, so a second computation inserted anywhere
        in between has to agree with the parser to stay green.
        """
        from pin_caps_gate import _parse_baseline

        for bounded in (True, False):
            content = _claude_md(real_pins=2, notes=12, bounded=bounded)
            parsed = _parse_pinned_section(content)
            assert parsed is not None
            assert _parse_baseline(content).bounded is parsed.bounded

    def test_the_two_parsers_agree_on_the_same_content(self):
        """`_parse_baseline` and `apply_edit_and_parse` must not disagree."""
        from pin_caps import apply_edit_and_parse
        from pin_caps_gate import _parse_baseline

        for bounded in (True, False):
            content = _claude_md(real_pins=2, notes=12, bounded=bounded)
            baseline = _parse_baseline(content)
            simulated = apply_edit_and_parse("", {"content": content})
            assert baseline.bounded is simulated.bounded
            assert len(baseline.pins) == len(simulated.pins)
            assert baseline.region_chars == simulated.region_chars

    def test_absent_section_is_bounded_so_enforcement_is_unchanged(self):
        """An absent region is exactly measurable, not untrustworthy.

        bounded=False here would switch the control OFF for every file
        with no Pinned Context section — a large population with no defect.
        """
        from pin_caps import apply_edit_and_parse
        from pin_caps_gate import _parse_baseline

        no_section = "# Some\nRandom content.\n"
        assert _parse_baseline(no_section) == ([], 0, True)
        assert apply_edit_and_parse("", {"content": no_section}) == ([], 0, True)

    def test_region_chars_reports_the_region_not_the_file(self):
        content = _claude_md(real_pins=2, notes=12, bounded=True)
        from pin_caps_gate import _parse_baseline

        state = _parse_baseline(content)
        assert 0 < state.region_chars < len(content)
