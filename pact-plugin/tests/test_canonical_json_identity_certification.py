"""Certification of the SHARING invariant: both marker families hash through
ONE serializer object.

WHAT THIS FILE COVERS THAT test_canonical_json_contract.py CANNOT. That file
pins the BYTES `shared.canonical_json.canonical_bytes` produces, against
hand-typed expectations, and it is the right protection for the three
serialization parameters. It exercises the SHARED OBJECT, so it stays GREEN
while the two families stop using that object. The header of canonical_json.py
enumerates the terms of the import contract and states that a change to the
module path or the exported name gives an ImportError. A FOURTH FAILURE MODE
IS NOT ON THAT LIST AND FAILS LOUDLY AT NO SITE:

  A SECOND DEFINITION. A re-added local `_canonical_bytes` in
  task_metadata_snapshot.py, or a second `json.dumps` in
  agent_handoff_marker.py, breaks NO import. The contract file keeps passing.
  The two families then compute DIFFERENT keys for one mapping, which is the
  divergence the extraction exists to prevent.

The protection against that was a prose line in the module header saying not
to re-add a local definition. A prose claim adjacent to a green suite is what
this arc measured as insufficient for the serialization parameters, and it is
the same shape here.

THE PROPERTY UNDER CERTIFICATION IS NOT THAT canonical_bytes SERIALIZES ONE
WAY. It is that BOTH FAMILIES HASH THROUGH THIS ONE OBJECT.

--------------------------------------------------------------------------
THE GUARD IS COPIED, NOT INVENTED, AND THE PRECEDENT IS NAMED
--------------------------------------------------------------------------
test_lock_identity_certification.py certifies shared-object identity for the
`file_lock` / `_atomic_write_text` pair through `__module__`, and its own
docstring records why `__module__` rather than `inspect.getsourcefile()`:
`functools.wraps` copies `__module__` through a decorator, so it stays
accurate, while `getsourcefile()` resolves a decorated wrapper to
contextlib.py for every twin and fails in both directions. This file uses the
same instrument for the same class of claim.

--------------------------------------------------------------------------
TWO INSTRUMENTS, BECAUSE ONE OF THE TWO FAILURE MODES IS INVISIBLE TO THE
FIRST
--------------------------------------------------------------------------
1. OBJECT IDENTITY (`__module__` plus `is`). This catches a REBOUND name: a
   family that defines its own `_canonical_bytes` and shadows the import.
2. A SOURCE SCAN for a second serializer. `__module__` CANNOT see this one.
   A module can keep importing the shared object, keep the binding correct,
   and call `json.dumps` at a NEW site beside it. The shared object stays
   right while the family stops going through it, so instrument 1 answers
   GREEN about a question it was not asked.

THE SOURCE SCAN PARSES, IT DOES NOT GREP, AND THAT IS LOAD-BEARING. Both
family modules discuss `json.dumps` IN PROSE, in the comments explaining why a
second serialization must not be added. A line-oriented search finds those
sentences and cannot separate them from a call. An AST walk sees calls and
does not see comments.
"""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import shared.agent_handoff_marker as marker  # noqa: E402
import shared.canonical_json as canonical  # noqa: E402
import shared.task_metadata_snapshot as snapshot  # noqa: E402

CANONICAL_MODULE = "shared.canonical_json"

# The two family modules and the name each one binds the shared serializer to.
# The snapshot family re-exports it under its historical module-private name,
# which is why the two names differ and why neither is a typo.
FAMILY_BINDINGS = (
    (snapshot, "_canonical_bytes"),
    (marker, "canonical_bytes"),
)

_FAMILY_SOURCES = (
    Path(snapshot.__file__),
    Path(marker.__file__),
)


def _serializer_calls(source_path: Path) -> list[str]:
    """Every `json.dumps` / `json.loads` call in one module, by dotted name.

    Parses rather than greps: the prose in both modules names `json.dumps`
    while calling it at no site, and a line search cannot tell those apart.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("dumps", "loads"):
            if isinstance(func.value, ast.Name) and func.value.id == "json":
                found.append(f"json.{func.attr}")
    return found


def _local_definitions(source_path: Path, names: tuple[str, ...]) -> list[str]:
    """Any module-level `def` in one module that shadows a shared name."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]


class TestBothFamiliesHashThroughOneObject:
    """The sharing invariant, certified rather than asserted in prose."""

    @pytest.mark.parametrize("module,binding", FAMILY_BINDINGS)
    def test_family_binding_comes_from_the_canonical_module(
        self, module, binding
    ):
        obtained = getattr(module, binding)
        assert obtained.__module__ == CANONICAL_MODULE, (
            f"{module.__name__}.{binding} came from "
            f"{obtained.__module__!r}, expected {CANONICAL_MODULE!r}. A "
            f"family that defines its own serializer breaks no import and "
            f"keeps the byte-contract test green while the two families "
            f"compute different keys for one mapping."
        )

    def test_the_two_families_bind_the_same_object(self):
        obtained = [getattr(mod, name) for mod, name in FAMILY_BINDINGS]
        assert obtained[0] is obtained[1] is canonical.canonical_bytes, (
            "the two marker families must hash through ONE object. Two "
            "objects that agree today are two serializations with nothing "
            "that makes them agree tomorrow."
        )

    @pytest.mark.parametrize("source_path", _FAMILY_SOURCES, ids=lambda p: p.name)
    def test_no_family_module_calls_a_second_serializer(self, source_path):
        """`__module__` cannot see this failure mode. See the header.

        A module can keep the shared import, keep the binding correct, and
        call json.dumps at a new site beside it.
        """
        calls = _serializer_calls(source_path)
        assert calls == [], (
            f"{source_path.name} calls {calls} directly. Every size "
            f"measurement, truncation head and content key in both families "
            f"must go through shared.canonical_json.canonical_bytes, or the "
            f"two families serialize one mapping two ways."
        )

    @pytest.mark.parametrize("source_path", _FAMILY_SOURCES, ids=lambda p: p.name)
    def test_no_family_module_redefines_the_serializer(self, source_path):
        shadowed = _local_definitions(
            source_path, ("canonical_bytes", "_canonical_bytes")
        )
        assert shadowed == [], (
            f"{source_path.name} defines {shadowed} locally, which shadows "
            f"the shared import without breaking it."
        )


class TestTheGuardIsNotVacuous:
    """A guard against a silent divergence that could not itself fail would
    RETIRE the concern while covering nothing. Each instrument is shown able
    to answer the other way."""

    def test_module_attribute_discriminates_a_local_definition(self):
        """The mechanism works, recorded as an arm rather than a comment so
        that a Python change making `__module__` non-discriminating fails
        HERE, loudly, rather than turning each assertion above into a
        tautology."""

        def _canonical_bytes(value):  # a stand-in for a re-added local
            return b""

        assert _canonical_bytes.__module__ != CANONICAL_MODULE
        assert canonical.canonical_bytes.__module__ == CANONICAL_MODULE
        assert _canonical_bytes is not canonical.canonical_bytes

    def test_the_source_scan_finds_a_call_and_ignores_the_prose(self, tmp_path):
        """The scan must separate a CALL from a SENTENCE, because both family
        modules carry the sentence and neither carries the call."""
        carries_a_call = tmp_path / "with_call.py"
        carries_a_call.write_text(
            "import json\n"
            "def f(v):\n"
            "    return json.dumps(v).encode()\n",
            encoding="utf-8",
        )
        prose_only = tmp_path / "prose_only.py"
        prose_only.write_text(
            '"""A second json.dumps here would be two serializations."""\n'
            "# Do not add a json.dumps below this line.\n"
            "VALUE = 1\n",
            encoding="utf-8",
        )
        assert _serializer_calls(carries_a_call) == ["json.dumps"]
        assert _serializer_calls(prose_only) == [], (
            "the scan matched a comment or a docstring. A line-oriented "
            "search does exactly that, which is why this one parses."
        )

    def test_the_definition_scan_finds_a_shadowing_def(self, tmp_path):
        shadowing = tmp_path / "shadowing.py"
        shadowing.write_text(
            "from .canonical_json import canonical_bytes\n"
            "def _canonical_bytes(v):\n"
            "    return b''\n",
            encoding="utf-8",
        )
        assert _local_definitions(
            shadowing, ("canonical_bytes", "_canonical_bytes")
        ) == ["_canonical_bytes"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
