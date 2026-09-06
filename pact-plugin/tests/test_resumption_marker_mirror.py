"""The resumption marker's event type, held together across the surfaces that
would otherwise disagree in silence.

WHAT IS COMPARED. `hooks/session_init.py` writes one event type when a
resumption claim surfaces. `agents/pact-secretary.md` instructs the secretary
to read that type at spawn, and `shared.session_journal` registers it so the
write is validated rather than falling through the unknown-type short-circuit.
The literal is the marker's ENTIRE identity — the event carries no fields, so
presence under the agreed type is the whole signal. A disagreement therefore
produces SILENCE, not an error: the hook writes one type, the secretary looks
for another and finds nothing, and the Working Memory rebuild the marker exists
to suppress runs anyway.

WHY THIS FILE EXISTS — MEASURED, NOT ASSUMED. Renaming the literal in
`hooks/session_init.py`, `tests/test_session_init.py`,
`hooks/shared/session_journal.py` and `tests/test_session_journal.py` — the
four places one refactor actually touches — while leaving the agent body alone
left the whole suite at its baseline: 15474 passed, 85 skipped, exit 0, zero
failures and zero errors. A SINGLE-sided rename is already caught, by the pin
in `tests/test_session_init.py` on the hook side and the one in
`skills/pact-handoff-harvest/test_skill_loading_harvest.py` on the agent side.
The COORDINATED rename was caught by nothing.

THE EXTRACTION NAMES NO LITERAL, and that is the whole design. A gate that
spells the event type out in order to find it cannot notice the event type
changing: it pins a constant rather than a relationship, and it reddens on a
legitimate rename of every surface at once. So the hook side is located
STRUCTURALLY — by the branch that guards the write — and whatever literal is
found there becomes the oracle the other two surfaces are checked against.

AN EMPTY EXTRACTION FAILS LOUDLY. When the anchor cannot be found the helper
raises instead of returning nothing, because a gate that compares an empty set
against anything agrees with everything.

THE BOUND, stated here because a guarded claim carrying none is what let this
gap stand. This gate catches a rename that moves one side alone, in either
direction. It PERMITS a rename of all three surfaces together — that is a
correct refactor, not a defect. It cannot see whether the secretary ACTS on the
marker it names: what an agent's context holds is not observable by any test
here, and no extension of this gate reaches it. And its scope is exactly the
surfaces that existed when it was written, so a fourth surface naming the
literal later would drift unchecked; that set is kept honest by census, not by
this file.

PRECEDENT, so a later reader knows the pattern was not invented here:
`tests/test_commands_structure.py` pins the `--type session_refresh_consumed`
literal in the command file that writes it, and `tests/test_audit_protocol.py`
holds the protocol extracts byte-identical against their SSOT region.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "session_init.py"
AGENT_BODY = PLUGIN_ROOT / "agents" / "pact-secretary.md"

# The branch that guards the marker write. Structural on purpose — see the
# module docstring: an anchor naming the literal cannot detect the literal
# moving.
SURFACING_BRANCH = "if resume_msg:"

_EVENT_CALL = re.compile(r'make_event\(\s*"([^"]+)"')


def marker_event_type(hook_source: str) -> str:
    """The event type written inside the resumption-surfacing branch.

    Raises on any ambiguity rather than returning a default. A caller handed
    nothing has no way to tell "the surfaces agree" from "there was nothing to
    compare", and the second reads as the first.
    """
    lines = hook_source.splitlines()
    at = [i for i, line in enumerate(lines) if line.strip() == SURFACING_BRANCH]
    if len(at) != 1:
        raise AssertionError(
            f"expected exactly one `{SURFACING_BRANCH}` line in the hook, "
            f"found {len(at)}. The marker write can no longer be located "
            "structurally. Re-anchor this gate on whatever now guards the "
            "write; do not delete it and do not fall back to naming the "
            "literal, which is the failure this gate exists to catch."
        )
    guard = at[0]
    indent = len(lines[guard]) - len(lines[guard].lstrip())
    body = []
    for line in lines[guard + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    found = _EVENT_CALL.findall("\n".join(body))
    if len(found) != 1:
        raise AssertionError(
            f"expected exactly one make_event(...) call inside the "
            f"`{SURFACING_BRANCH}` branch, found {len(found)}. An empty "
            "extraction must never pass as agreement."
        )
    return found[0]


@pytest.fixture(scope="module")
def event_type():
    return marker_event_type(HOOK.read_text(encoding="utf-8"))


class TestTheResumptionMarkerTypeAgreesAcrossItsSurfaces:
    """The hook is the oracle; the other two surfaces are checked against it."""

    def test_the_agent_body_names_the_type_the_hook_writes(self, event_type):
        """Detects: a rename coordinated across every hook-side surface that
        leaves the agent body naming the old type.

        This is the consequential direction. The secretary reads the marker to
        learn that this session resumes an arc still under judgement; reading a
        type nothing writes returns null, which is indistinguishable from a
        fresh start, so the rebuild runs and the agents respawned to judge the
        arc are handed the arc's own conclusions.
        """
        assert event_type in AGENT_BODY.read_text(encoding="utf-8"), (
            f"hooks/session_init.py writes {event_type!r}, but "
            f"agents/pact-secretary.md does not name it. The secretary reads "
            "the marker by type; a type nothing writes reads as no resumption."
        )

    def test_the_journal_registers_the_type_the_hook_writes(self, event_type):
        """Detects: a rename at the write site that leaves the registration
        table behind.

        Milder than the sibling above and still silent. `_validate_event_schema`
        short-circuits on an unregistered type, so the write still succeeds —
        it simply stops being validated, and nothing says so.
        """
        from shared.session_journal import _REQUIRED_FIELDS_BY_TYPE

        assert event_type in _REQUIRED_FIELDS_BY_TYPE, (
            f"hooks/session_init.py writes {event_type!r}, which is not "
            "registered in _REQUIRED_FIELDS_BY_TYPE. An unregistered type "
            "skips validation silently rather than failing."
        )


class TestTheExtractionCannotAgreeWithNothing:
    """The gate above is only worth its green if it can be made to fail."""

    def test_a_missing_surfacing_branch_raises(self):
        """Detects: this gate quietly becoming vacuous because its anchor moved.

        Without this, a refactor that renames the guard variable turns the
        extraction into a no-op, and a no-op reports agreement.
        """
        with pytest.raises(AssertionError, match="found 0"):
            marker_event_type("def f():\n    if resumption:\n        pass\n")

    def test_a_branch_with_no_write_raises(self):
        """Detects: the marker write being deleted while the branch survives.

        The extraction must refuse an empty result rather than hand back a
        literal found somewhere else in the file.
        """
        source = (
            "def f():\n"
            "    if resume_msg:\n"
            "        context_parts.append(resume_msg)\n"
        )
        with pytest.raises(AssertionError, match="found 0"):
            marker_event_type(source)
