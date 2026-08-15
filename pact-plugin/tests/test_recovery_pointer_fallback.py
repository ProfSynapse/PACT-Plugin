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
2. THE UN-PATCHED OVER-BOUND PATH IS OUT OF SCOPE AND IS NOT ARMED IN EITHER
   DIRECTION. With the sanitize working, an id longer than the identifier
   bound is CUT to the bound with a truncation marker, which is non-empty, so
   the fallback below never runs and the emitted pointer is truncated. That
   truncated pointer is present and does not resolve, which is the shape the
   acceptor exists to avoid, and it is a SEPARATE open finding on the write
   side at `_REFRESH_IDENTIFIER_TRUNCATION_LIMIT`, blocked on an ingress
   census. Arming it here in either direction would be incorrect: asserting no
   line contradicts the code, and asserting the truncated line would PIN AN
   OPEN DEFECT. The refusal arms below therefore run in the forced-empty state,
   where the acceptor is the party under test.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts")
)

_ORDINARY_ID = "a1b2c3d4-e5f6"


def _install_probe(monkeypatch, module):
    """Force the sanitize to fail, and record each acceptor call.

    Returns the list the wrapper appends to. An empty list means the fallback
    did not run, which is the difference between a fired fallback and a
    working sanitize.
    """
    monkeypatch.setattr(module, "_sanitize_prompt_field", lambda *_a, **_k: "")
    calls = []
    real = module._recover_identifier

    def recorder(raw):
        calls.append(raw)
        return real(raw)

    monkeypatch.setattr(module, "_recover_identifier", recorder)
    return calls


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
        """The acceptor refuses an over-bound id rather than cutting it.

        SCOPE, AND IT IS NARROW BY DESIGN: this is the acceptor's refusal in
        the forced-empty state. It says nothing about the un-patched path,
        where the working sanitize CUTS an over-bound id and the fallback never
        runs. See the note at the top of this file.
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
        calls = []
        real = working_memory._recover_identifier

        def recorder(raw):
            calls.append(raw)
            return real(raw)

        monkeypatch.setattr(working_memory, "_recover_identifier", recorder)

        entry = working_memory._format_memory_entry(
            {"context": "a context"}, memory_id=_ORDINARY_ID
        )

        assert calls == [], (
            f"the fallback ran with a working sanitize. calls: {calls}"
        )
        assert _pointer_lines(entry, working_memory) == [
            f"{working_memory._MEMORY_ID_LABEL}: {_ORDINARY_ID}"
        ]
