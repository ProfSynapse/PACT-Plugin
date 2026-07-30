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
