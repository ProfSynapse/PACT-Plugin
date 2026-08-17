"""The SubagentStart registration must select an in-process teammate spawn.

WHAT WENT WRONG. ``hooks/peer_inject.py`` builds the per-spawn PACT context
block (role marker, charter pointer, peer list, plugin banner, teachback
reminder, completion-authority note). It was registered on SubagentStart
behind a matcher that listed the twelve ``pact-*`` agent-type literals. The
platform does NOT put the PACT agent type in the field a SubagentStart matcher
reads for an in-process teammate. It puts the TEAMMATE NAME there, and it
carries the PACT type in a different field. So the matcher selected no
teammate spawn, the hook did not run, and the block reached nobody.

MEASURED, with the parameter beside each count. Population: the 155 files
matching ``subagents/*.meta.json`` for one team session, which is the
platform's own record of each spawn.
  - ``taskKind`` is ``in_process_teammate`` in 153 of 155.
  - ``agentType`` matches the twelve-literal matcher in 0 of 155.
  - ``agentType`` does not match while ``customAgentType`` DOES match in
    152 of 155.

WHY THE FAILURE WAS SILENT, which is what these arms answer. ``peer_inject``
is fail-open by contract: a hook error must not block a spawn, so it prints
``suppressOutput`` and exits 0. A hook that never runs and a hook that runs
and declines are therefore IDENTICAL from outside, and no log separates them.
An arm that watches the hook OUTPUT cannot tell the two apart. So these arms
watch the REGISTRATION instead, which is the gate that actually decided, and
they evaluate it against the measured platform frame shape.

THE SEPARATING PROPERTY, stated for each arm below: given a spawn frame whose
``agentType`` is a teammate NAME, does the registration select it? A1 answers
that question and reddens on the wording that shipped. A2 holds the other
half, so a repair cannot buy A1 by dropping the Agent-tool spawn shape.
"""
import json
import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

# The measured platform frame shapes. A teammate name is user-chosen, so no
# matcher can enumerate the first row: only an unmatched registration selects it.
TEAMMATE_FRAME_AGENT_TYPES = ("carrier", "control", "coder-scope", "plan-architect")
AGENT_TOOL_FRAME_AGENT_TYPES = ("pact-backend-coder", "pact-secretary")


def _subagent_start_entries_registering(hook_filename: str) -> list[dict]:
    """Every SubagentStart registration block whose command names the hook."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    out = []
    for entry in data.get("hooks", {}).get("SubagentStart", []):
        for hook in entry.get("hooks", []):
            if hook_filename in hook.get("command", ""):
                out.append(entry)
                break
    return out


def _selects(entry: dict, agent_type: str) -> bool:
    """Does this registration select a frame with this agent type?

    A registration with no ``matcher`` key selects every frame. A registration
    with a ``matcher`` selects a frame when the pattern matches the type.
    """
    pattern = entry.get("matcher")
    if pattern is None:
        return True
    return re.fullmatch(pattern, agent_type) is not None


@pytest.fixture(scope="module")
def entry() -> dict:
    """The single SubagentStart registration for peer_inject.

    Fails loudly on absence, so a removal or a rename cannot leave the arms
    below measuring nothing.
    """
    entries = _subagent_start_entries_registering("peer_inject.py")
    assert len(entries) == 1, (
        f"expected exactly 1 SubagentStart registration naming peer_inject.py, "
        f"found {len(entries)}. The per-spawn PACT context block is delivered "
        f"by that registration alone; without it these arms measure nothing."
    )
    return entries[0]


class TestA1SelectsAnInProcessTeammate:
    """The measured teammate frame shape must be selected.

    SEPARATING PROPERTY: agentType is a teammate NAME. The shipped
    twelve-literal matcher selects none of these, which is the defect.
    """

    @pytest.mark.parametrize("agent_type", TEAMMATE_FRAME_AGENT_TYPES)
    def test_teammate_named_frame_is_selected(self, entry, agent_type):
        assert _selects(entry, agent_type), (
            f"the SubagentStart registration does not select a spawn frame whose "
            f"agentType is {agent_type!r}. Measured: the platform puts the "
            f"TEAMMATE NAME in that field for an in-process teammate and carries "
            f"the PACT type in a different field, so a matcher listing pact-* "
            f"literals selects 0 teammate spawns and the context block reaches "
            f"nobody. A teammate name is user-chosen, so no matcher can "
            f"enumerate it: the registration must carry no matcher."
        )


class TestA2KeepsTheAgentToolFrame:
    """The other half of the population must stay selected, so a repair cannot
    buy A1 by trading away the Agent-tool spawn shape."""

    @pytest.mark.parametrize("agent_type", AGENT_TOOL_FRAME_AGENT_TYPES)
    def test_pact_typed_frame_is_still_selected(self, entry, agent_type):
        assert _selects(entry, agent_type), (
            f"the registration no longer selects a spawn frame whose agentType "
            f"is {agent_type!r}. That is the Agent-tool spawn shape, and it was "
            f"selected before this repair."
        )


class TestA3TheRegistrationIsWellFormed:
    """Structural floor: the block is registered as a command hook, so a
    malformed edit is loud rather than silently unselectable."""

    def test_entry_registers_a_command_hook(self, entry):
        commands = [h.get("command", "") for h in entry.get("hooks", [])]
        assert any("peer_inject.py" in c for c in commands), (
            "the SubagentStart entry no longer runs peer_inject.py"
        )
        assert all(h.get("type") == "command" for h in entry.get("hooks", [])), (
            "a SubagentStart hook in this entry is not a command hook"
        )
