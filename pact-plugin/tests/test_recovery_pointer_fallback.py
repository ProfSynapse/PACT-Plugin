"""The recovery pointer survives a failure of the guard that bounds it.

WHAT THE POINTER IS FOR. The entry-cut design accepts TRUNCATION rather than
refusal, and the whole of that acceptance rests on one condition: the
`**Memory ID**` line survives, so the loss at that rendering is recoverable
from the store. A path that drops the pointer spends the guarantee the cut rule
rests on.

THE PATH THAT DROPPED IT. `_sanitize_prompt_field` catches bare `Exception` and
returns `""`, and the two recovery-key sites gate on the TRUTHINESS of its
output, so an internal failure inside the guard removed the pointer line in
silence. The helper cannot report WHY it returned empty, so the discriminator
is built at the caller: a NON-EMPTY input with an EMPTY output.

WHY THESE ARMS ASSERT BYTE EQUALITY AND NOT PRESENCE. The ruled design is an
ACCEPTOR: `_recover_identifier` returns the input UNCHANGED or nothing, so an
emitted pointer resolves against the store BY CONSTRUCTION. A labelled marker
was considered and REJECTED, because a labelled empty value reproduces the
defect this branch carries elsewhere: a pointer that is PRESENT and does NOT
RESOLVE. AN ARM THAT ASSERTED A LINE WAS PRESENT WOULD BE GREEN FOR THE
REJECTED DESIGN TOO, so it would not test the ruling at all. Equality with the
input is the assertion that separates the two.

THE PATCH SEAM IS INSTRUMENTED, BECAUSE A PATCH THAT MISSED WOULD LOOK LIKE A
PASS. If the forced failure did not reach the call site, the sanitize would
work, the line would be present, and an equality assertion would hold for the
wrong cause. So `_recover_identifier` is wrapped with a recorder, and each arm
asserts WHETHER IT RAN. The two directions together (it ran here, it did not
run in the control) are what prove the instrument is live.

WHAT THESE ARMS DO NOT COVER, STATED RATHER THAN LEFT TO BE FOUND.
1. LIVE REACHABILITY. No natural input is known that makes the shipped
   sanitize return empty for a non-empty id. These arms hold a CONDITIONAL: IF
   the guard returns empty for a non-empty id, THEN the pointer survives
   byte-identical. They do not claim the state is reachable in production.
2. THE INGRESS. Nothing bounds the identifier where it ENTERS the store, and
   no seat has measured which callers can supply one longer than the bound.
   The generator emits 32 characters against a bound of 64, so this path
   needs a caller the generator is not. `TestAnIdLongerThanTheBoundEmitsNoPointer`
   below makes the OUTPUT honest for such a value. It does not stop the value
   entering, and nothing tells a reader that one arrived: a REFUSED pointer is
   silent at the emit site, as an ABSENT one is.

THE SECOND CLASS BELOW CLOSED A DEFECT THIS FILE ONCE DECLARED OUT OF SCOPE,
AND THE HISTORY IS KEPT BECAUSE THE REASONING STAYS CORRECT. With the sanitize
at work, an id longer than the bound was CUT to the bound with a truncation
marker. A cut value is NON-EMPTY, so the empty-output gate could not fire, the
acceptor was unreachable and its own length refusal was dead code. The emitted
pointer was PRESENT and did NOT RESOLVE, which is the shape the acceptor exists
to avoid. Arming that state was correctly refused at the time, because
asserting the cut line would have PINNED AN OPEN DEFECT. The source now defers
that id to the acceptor, so the arms assert the REFUSAL rather than the cut.
"""
import ast
import sys
from pathlib import Path

import pytest

_SOURCE_PATH = (
    Path(__file__).parent.parent
    / "skills" / "pact-memory" / "scripts" / "working_memory.py"
)

sys.path.insert(
    0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts")
)

_ORDINARY_ID = "a1b2c3d4-e5f6"


def _record_acceptor_calls(monkeypatch, module):
    """Wrap the acceptor with a recorder, and leave the sanitize alone.

    Returns the list the wrapper appends to. An empty list means the acceptor
    did not run. THE RECORDER DELEGATES TO THE REAL ACCEPTOR, so the arms
    measure the shipped decision and not the wrapper.
    """
    calls = []
    real = module._recover_identifier

    def recorder(raw):
        calls.append(raw)
        return real(raw)

    monkeypatch.setattr(module, "_recover_identifier", recorder)
    return calls


def _install_probe(monkeypatch, module):
    """Force the sanitize to fail, and record each acceptor call.

    Returns the list the wrapper appends to. An empty list means the fallback
    did not run, which is the difference between a fired fallback and a
    working sanitize.
    """
    monkeypatch.setattr(module, "_sanitize_prompt_field", lambda *_a, **_k: "")
    return _record_acceptor_calls(monkeypatch, module)


def _pointer_lines(entry, module):
    return [
        line
        for line in entry.splitlines()
        if line.startswith(module._MEMORY_ID_LABEL)
    ]


@pytest.fixture
def working_memory():
    import working_memory as module

    return module


class TestRecoveryPointerSurvivesAGuardFailure:
    """The ruled property at both formatters, its two refusals and a control."""

    def test_the_saved_entry_emits_the_id_byte_identical_to_its_input(
        self, working_memory, monkeypatch
    ):
        """Forced empty in, unchanged id out, at the save-path formatter."""
        calls = _install_probe(monkeypatch, working_memory)
        # LIVENESS OF THE PATCH ITSELF, checked through the module attribute
        # the call site reads.
        assert working_memory._sanitize_prompt_field("not empty", 64) == ""

        entry = working_memory._format_memory_entry(
            {"context": "a context", "goal": "a goal"}, memory_id=_ORDINARY_ID
        )

        assert calls == [_ORDINARY_ID], (
            "the fallback did not run, so the assertion below would describe "
            f"the sanitize rather than the acceptor. calls: {calls}"
        )
        lines = _pointer_lines(entry, working_memory)
        assert lines == [f"{working_memory._MEMORY_ID_LABEL}: {_ORDINARY_ID}"], (
            "the emitted pointer is not byte-identical to the id received, so "
            f"it does not resolve by construction. got: {lines}"
        )

    def test_the_retrieved_entry_emits_the_id_byte_identical_to_its_input(
        self, working_memory, monkeypatch
    ):
        """Forced empty in, unchanged id out, at the retrieve-path formatter.

        The two formatters carry the same repair, so the arm is repeated
        rather than shared: a repair applied to one site alone is the failure
        this pair exists to catch.
        """
        calls = _install_probe(monkeypatch, working_memory)
        assert working_memory._sanitize_prompt_field("not empty", 64) == ""

        entry = working_memory._format_retrieved_entry(
            {"context": "a context", "goal": "a goal"},
            query="a query",
            memory_id=_ORDINARY_ID,
        )

        assert calls == [_ORDINARY_ID], f"calls: {calls}"
        lines = _pointer_lines(entry, working_memory)
        assert lines == [f"{working_memory._MEMORY_ID_LABEL}: {_ORDINARY_ID}"], (
            f"got: {lines}"
        )

    def test_an_id_of_control_characters_alone_emits_no_pointer(
        self, working_memory, monkeypatch
    ):
        """The acceptor refuses rather than emits a value that cannot resolve.

        Where no key can be recovered, an ABSENT line is honest and a labelled
        empty value is not.
        """
        control_chars = "\x00\x01\x02\x1f"
        calls = _install_probe(monkeypatch, working_memory)

        entry = working_memory._format_memory_entry(
            {"context": "a context"}, memory_id=control_chars
        )

        assert calls == [control_chars], (
            f"the acceptor did not run, so no refusal was tested. {calls}"
        )
        assert _pointer_lines(entry, working_memory) == []

    def test_an_over_bound_id_emits_no_pointer_when_the_guard_has_failed(
        self, working_memory, monkeypatch
    ):
        """The acceptor refuses an id past the bound rather than cutting it.

        SCOPE, AND IT IS NARROW BY DESIGN: this is the acceptor's refusal in
        the FORCED-EMPTY state, where the empty output is what routes the id
        to the acceptor. The same refusal on the WORKING sanitize path, where
        the LENGTH test is what routes it, belongs to
        `TestAnIdLongerThanTheBoundEmitsNoPointer` below. The two routes reach
        one acceptor, and each needs its own arm.
        """
        over_bound = "z" * (working_memory._REFRESH_IDENTIFIER_TRUNCATION_LIMIT + 1)
        calls = _install_probe(monkeypatch, working_memory)

        entry = working_memory._format_memory_entry(
            {"context": "a context"}, memory_id=over_bound
        )

        assert calls == [over_bound], f"{calls}"
        assert _pointer_lines(entry, working_memory) == []

    def test_control_a_working_guard_does_not_reach_the_fallback(
        self, working_memory, monkeypatch
    ):
        """THE CONTROL. With the sanitize at work the acceptor must NOT run.

        Without this, an acceptor wired to run on EVERY id would satisfy each
        arm above, and the discriminator that gates it would be untested.
        """
        calls = _record_acceptor_calls(monkeypatch, working_memory)

        entry = working_memory._format_memory_entry(
            {"context": "a context"}, memory_id=_ORDINARY_ID
        )

        assert calls == [], (
            f"the fallback ran with a working sanitize. calls: {calls}"
        )
        assert _pointer_lines(entry, working_memory) == [
            f"{working_memory._MEMORY_ID_LABEL}: {_ORDINARY_ID}"
        ]


class TestAnIdLongerThanTheBoundEmitsNoPointer:
    """The WORKING sanitize path refuses an id longer than the bound.

    THE STATE THESE ARMS COVER IS THE ONE THE CLASS ABOVE CANNOT REACH. The
    arms above force the sanitize to return empty, which is what puts the
    acceptor in the path. With the sanitize AT WORK, an id longer than the
    bound was CUT to the bound and emitted, because a cut value is non-empty
    and the empty-output gate could not fire. The acceptor was unreachable
    there and its own length refusal was dead code.

    WHY NO LINE IS THE CORRECT OUTPUT, AND THE THIRD CASE IS THE ONE THAT
    DECIDES IT. An ABSENT line says no key is here. A labelled EMPTY value
    says the key is empty, which is visibly broken. A CUT value says here is
    the key, and it is INDISTINGUISHABLE from a good one. So it fails at the
    READER, far from the writer, and it reads as a loss in the store rather
    than as a loss at the rendering. That is worse than the two cases the
    acceptor docstring weighs, and it is why this path refuses.

    EACH ARM ASSERTS TWO HALVES, AND ONE HALF ALONE IS NOT ENOUGH. The
    OUTPUT half alone stays green for a repair that dropped the field
    completely. The INSTRUMENT half alone stays green for a repair that
    called the acceptor and then emitted the cut value anyway. The two
    together say that the acceptor ruled, and that its refusal reached the
    output.
    """

    def _over_bound_id(self, module):
        return "z" * (module._REFRESH_IDENTIFIER_TRUNCATION_LIMIT + 1)

    def test_the_saved_entry_emits_no_pointer_for_an_id_past_the_bound(
        self, working_memory, monkeypatch
    ):
        """Working sanitize, id past the bound, no pointer, at the save path."""
        over_bound = self._over_bound_id(working_memory)
        calls = _record_acceptor_calls(monkeypatch, working_memory)

        entry = working_memory._format_memory_entry(
            {"context": "a context"}, memory_id=over_bound
        )

        lines = _pointer_lines(entry, working_memory)
        assert calls == [over_bound], (
            "the acceptor did not rule this id, so the sanitize decided the "
            f"emitted value alone. calls: {calls}. emitted: {lines}"
        )
        assert lines == [], (
            "a pointer line survived for an id longer than the bound, so the "
            f"emitted key cannot resolve against the store. got: {lines}"
        )

    def test_the_retrieved_entry_emits_no_pointer_for_an_id_past_the_bound(
        self, working_memory, monkeypatch
    ):
        """The same property at the retrieve path.

        The two formatters carry the same block, so the arm is repeated
        rather than shared: a repair applied to one site alone is the failure
        this pair exists to catch.
        """
        over_bound = self._over_bound_id(working_memory)
        calls = _record_acceptor_calls(monkeypatch, working_memory)

        entry = working_memory._format_retrieved_entry(
            {"context": "a context"}, query="a query", memory_id=over_bound
        )

        lines = _pointer_lines(entry, working_memory)
        assert calls == [over_bound], (
            f"calls: {calls}. emitted: {lines}"
        )
        assert lines == [], (
            "a pointer line survived at the retrieve path for an id longer "
            f"than the bound. got: {lines}"
        )


class TestEachIdentifierBoundSiteCarriesTheRefusal:
    """A THIRD emit site cannot appear without this guard going red.

    TWO IDENTICAL BLOCKS IN ONE FILE IS A SHAPE THAT GROWS. A later author
    who adds a third formatter will copy the block that was correct when
    they read it. The two arms above drive the two formatters BY NAME, so
    they say nothing about a site that does not exist yet.

    THIS GUARD DISCOVERS ITS OWN TARGETS RATHER THAN LISTS THEM. It walks
    the shipped source for each function that bounds a value with
    `_REFRESH_IDENTIFIER_TRUNCATION_LIMIT` through the sanitize, and it
    requires that same function to compare against the bound AND to call the
    acceptor. A guard that carried a list of two function names would go
    green in its own genus, which is the failure it exists to prevent.
    """

    _SANITIZE = "_sanitize_prompt_field"
    _ACCEPTOR = "_recover_identifier"
    _LIMIT = "_REFRESH_IDENTIFIER_TRUNCATION_LIMIT"

    def _functions_that_bound_an_identifier(self):
        """Return the name of each function that sanitizes at the id bound."""
        tree = ast.parse(_SOURCE_PATH.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                if getattr(inner.func, "id", None) != self._SANITIZE:
                    continue
                bounds = [
                    a for a in inner.args
                    if isinstance(a, ast.Name) and a.id == self._LIMIT
                ]
                if bounds:
                    found.append(node)
                    break
        return found

    def test_every_identifier_bound_site_compares_and_defers(self):
        sites = self._functions_that_bound_an_identifier()

        # NON-VACUITY. A population of zero passes each check below without
        # reading one line of the source, and it is what a rename of the
        # sanitize or of the constant produces.
        assert len(sites) >= 2, (
            f"found {len(sites)} site(s) that bound a value with "
            f"{self._LIMIT}, and the two known formatters give 2. The walk "
            "matched nothing, so this guard measured an empty set. Check for "
            "a rename of the sanitize or of the constant."
        )

        for site in sites:
            names = {
                inner.func.id
                for inner in ast.walk(site)
                if isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
            }
            compares = [
                inner for inner in ast.walk(site)
                if isinstance(inner, ast.Compare)
                and any(
                    isinstance(operand, ast.Name) and operand.id == self._LIMIT
                    for operand in [inner.left] + list(inner.comparators)
                )
            ]
            assert self._ACCEPTOR in names, (
                f"{site.name} bounds an identifier with {self._LIMIT} and "
                f"does not call {self._ACCEPTOR}. The sanitize CUTS a value "
                "past the bound, and a cut pointer is present and does not "
                "resolve. Defer the ruling to the acceptor."
            )
            assert compares, (
                f"{site.name} calls {self._ACCEPTOR} and does not compare "
                f"against {self._LIMIT}. Without that comparison the "
                "acceptor is reached only when the sanitize returns empty, "
                "so an id past the bound is cut and emitted."
            )
