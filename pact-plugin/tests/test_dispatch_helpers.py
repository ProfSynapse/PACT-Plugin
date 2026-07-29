"""Direct unit coverage for shared/dispatch_helpers.py structural predicates.

Housed in its OWN file rather than a consumer's: these predicates are shared
infrastructure with more than one consumer, so coverage that lives inside any
single consumer's test file dies when that consumer is refactored or retired —
the predicate would silently lose its only direct tests with nothing going red.

Scope here is the PURE predicates (no FS, no team config, no context). The
resolution helpers that read team config are exercised against a seeded config
in the consumer suites.

is_owner_wiring_shape recognizes ONE leg of the three-leg dispatch
recognition — the SHAPE of an owner-wiring write. The other two legs (owner
resolves to a pact specialist; subject is not a teachback gate) and the
per-consumer exemption predicate are deliberately NOT its business; the
scope-boundary tests at the bottom are what keep them out.

Note on vocabulary: handoff_ordering_gate calls this write "terminal", a term
that file DEFINES locally as "both halves present" (as against a partial
one-half write). The shared helper says "shape" instead because that local
definition does not travel to a module with several consumers — the two names
describe the same predicate, not different ones.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared.dispatch_helpers import (  # noqa: E402
    is_owner_wiring_shape,
    merged_variety_stamp,
)


def _wiring(owner="backend-coder", add_blocked_by=("A",), **extra):
    """An owner-wiring tool_input: owner + addBlockedBy in the same write."""
    ti = {"taskId": "42"}
    if owner is not None:
        ti["owner"] = owner
    if add_blocked_by is not None:
        ti["addBlockedBy"] = list(add_blocked_by)
    ti.update(extra)
    return ti


class TestFiresOnTheTerminalWiringShape:
    def test_owner_and_addblockedby_together(self):
        assert is_owner_wiring_shape(_wiring()) is True

    def test_multiple_blockers(self):
        assert is_owner_wiring_shape(_wiring(add_blocked_by=("A", "B"))) is True

    def test_owner_with_surrounding_whitespace_still_fires(self):
        """Non-blank after strip() is the bar; the RAW value is what the
        caller forwards to the owner->agentType resolution, so this predicate
        must not normalize it away."""
        assert is_owner_wiring_shape(_wiring(owner="  backend-coder  ")) is True


class TestPartialWiringDoesNotFire:
    """Either half alone is a non-terminal write, not a dispatch. TaskCreate(B)
    leaves owner empty; every other addBlockedBy use in the templates carries no
    owner in the same call."""

    def test_owner_only(self):
        assert is_owner_wiring_shape(_wiring(add_blocked_by=None)) is False

    def test_addblockedby_only(self):
        assert is_owner_wiring_shape(_wiring(owner=None)) is False

    def test_neither(self):
        assert is_owner_wiring_shape({"taskId": "42"}) is False

    def test_empty_addblockedby_list(self):
        assert is_owner_wiring_shape(_wiring(add_blocked_by=())) is False


@pytest.mark.parametrize("owner", ["", "   ", "\t\n", None, 7, 0, ["x"], {"a": 1}, True])
def test_unusable_owner_never_fires(owner):
    """Empty / whitespace-only / non-str owners all fail closed. A whitespace
    owner passes a bare truthiness check but is not a resolvable member name."""
    ti = _wiring(owner=None)
    if owner is not None:
        ti["owner"] = owner
    assert is_owner_wiring_shape(ti) is False


@pytest.mark.parametrize("blockers", ["A", "", 1, 0, {"0": "A"}, set(), None, True])
def test_non_list_addblockedby_never_fires(blockers):
    """A bare string is the dangerous one: 'A' is truthy and iterable, so a
    check without the isinstance(list) leg would wave it through."""
    ti = _wiring(add_blocked_by=None)
    if blockers is not None:
        ti["addBlockedBy"] = blockers
    assert is_owner_wiring_shape(ti) is False


@pytest.mark.parametrize("bad", [None, "", [], 0, 42, "tool_input", ("owner",), set()])
def test_non_dict_input_returns_false_and_never_raises(bad):
    """Contract is total: the callers invoke this on unvalidated hook stdin."""
    assert is_owner_wiring_shape(bad) is False


class TestScopeBoundary:
    """TRIPWIRES on what this predicate must NOT grow into. Each of these is a
    leg that belongs to a different layer; if one migrates in here, the shared
    helper stops being reusable by consumers that ask a different question, and
    the two exemption policies the source forbids recoupling get recoupled.
    """

    def test_does_not_judge_owner_name_shape(self):
        """Real owners are BARE names; 'pact-*' is the team-config agentType.
        This predicate must apply NO name-shape rule in either direction —
        that resolution belongs to is_pact_specialist_owner. Reds if someone
        adds an owner.startswith('pact-') test (or its inverse) here."""
        assert is_owner_wiring_shape(_wiring(owner="backend-coder")) is True
        assert is_owner_wiring_shape(_wiring(owner="pact-backend-coder")) is True
        assert is_owner_wiring_shape(_wiring(owner="secretary")) is True
        assert is_owner_wiring_shape(_wiring(owner="literally-anything")) is True

    def test_does_not_read_subject(self):
        """The teachback-subject carve-out is a separate leg applied by the
        caller. A teachback-shaped subject in the same tool_input must not
        change this predicate's answer."""
        assert is_owner_wiring_shape(
            _wiring(subject="backend-coder: TEACHBACK for the thing")
        ) is True

    def test_does_not_read_exemption_metadata(self):
        """No exemption leg belongs here, and specifically no completion_type
        or metadata.type test: whether signal-shaped dispatches are variety-
        exempt is an unresolved protocol question, and encoding an answer in
        this shared predicate would settle it by implementation."""
        assert is_owner_wiring_shape(
            _wiring(metadata={"completion_type": "signal", "type": "blocker"})
        ) is True

    def test_is_pure_no_context_required(self):
        """No pact_context.init(), no team config, no task store, no HOME —
        the predicate answers from tool_input alone. If it ever needs setup,
        this test breaks at collection rather than passing quietly."""
        assert is_owner_wiring_shape(_wiring()) is True
        assert is_owner_wiring_shape({"owner": "x"}) is False


# =============================================================================
# merged_variety_stamp — the disk/incoming overlay both the enforcement gate
# and the dispatch_site emit resolve through.
# =============================================================================
D11 = {
    "novelty": 3, "novelty_rationale": "x",
    "scope": 3, "scope_rationale": "x",
    "uncertainty": 3, "uncertainty_rationale": "x",
    "risk": 3, "risk_rationale": "x",
    "total": 12,
}


def _task(variety=None, **metadata_extra):
    md = dict(metadata_extra)
    if variety is not None:
        md["variety"] = variety
    return {"id": "42", "metadata": md} if md else {"id": "42"}


class TestMergedVarietyStampLevel:
    """THE LEVEL IS THE PROPERTY, not an implementation detail. Merging the
    METADATA dicts instead of the VARIETY keys lets a write that names
    `variety` at all replace the on-disk stamp wholesale — which resolves to
    no total and manufactures the false 'un-stamped' reading the overlay
    exists to remove. These pins fail under that reading and pass under this
    one, which is the only difference between the two implementations.
    """

    def test_partial_incoming_does_NOT_wipe_a_complete_disk_stamp(self):
        """The discriminator. Under a metadata-level merge the result is
        `{"novelty": 4}` and every other key is gone; under the key-level
        merge the disk keys survive and only `novelty` is overwritten."""
        merged = merged_variety_stamp(
            {"metadata": {"variety": {"novelty": 4}}}, _task(D11),
        )
        assert merged["novelty"] == 4, "the incoming write must win on its key"
        assert merged["total"] == 12, (
            "a one-key re-stamp wiped the disk total — this is the "
            "metadata-level merge, and it turns a stamped dispatch into an "
            "un-stamped one"
        )
        assert merged["scope"] == 3 and merged["risk"] == 3

    def test_incoming_wins_on_a_key_it_names(self):
        merged = merged_variety_stamp(
            {"metadata": {"variety": {"total": 8}}}, _task(D11),
        )
        assert merged["total"] == 8

    def test_disk_alone_when_the_write_carries_no_variety(self):
        assert merged_variety_stamp({"metadata": {"handoff": {}}}, _task(D11)) == D11

    def test_incoming_alone_when_disk_is_empty(self):
        """The atomic wire+stamp: the stamp exists only in the write."""
        assert merged_variety_stamp({"metadata": {"variety": D11}}, _task()) == D11


class TestMergedVarietyStampIsUnfiltered:
    def test_keeps_non_canonical_keys_the_journal_projection_drops(self):
        """UNFILTERED BY DESIGN. `score` is a legal resolve_variety_total
        candidate and is NOT in DISPATCH_VARIETY_KEYS, so projecting here
        would deny a stamp that resolves today. Reds if someone 'tidies' this
        by reusing the emit's projection."""
        merged = merged_variety_stamp({}, _task({"score": 12}))
        assert merged == {"score": 12}

    def test_keeps_the_rationale_strings(self):
        """The emit drops these; the merge must not, or the two consumers
        stop being able to differ."""
        merged = merged_variety_stamp({}, _task(D11))
        assert merged["novelty_rationale"] == "x"


class TestMergedVarietyStampIsTotalAndReadOnly:
    @pytest.mark.parametrize("tool_input", [None, "", 0, [], "notadict"])
    def test_non_dict_tool_input_contributes_nothing(self, tool_input):
        assert merged_variety_stamp(tool_input, _task(D11)) == D11

    @pytest.mark.parametrize("task", [None, "", 0, [], "notadict"])
    def test_non_dict_task_contributes_nothing(self, task):
        assert merged_variety_stamp({"metadata": {"variety": D11}}, task) == D11

    @pytest.mark.parametrize("md", [None, "x", 7, [], {"variety": "notadict"},
                                    {"variety": None}, {}])
    def test_hostile_metadata_never_raises(self, md):
        assert isinstance(merged_variety_stamp({"metadata": md}, {"metadata": md}), dict)

    def test_both_empty_is_an_empty_DICT_not_None(self):
        """Load-bearing at the gate: resolve_variety_total early-returns None
        on a non-dict `variety`, which makes its metadata.variety_score
        candidate unreachable. Returning {} rather than None is what keeps
        that candidate live."""
        assert merged_variety_stamp({}, {}) == {}

    def test_does_not_mutate_either_input(self):
        task = _task(dict(D11))
        tool_input = {"metadata": {"variety": {"novelty": 4}}}
        before_task = json.loads(json.dumps(task))
        before_input = json.loads(json.dumps(tool_input))
        merged_variety_stamp(tool_input, task)
        assert task == before_task, "the disk task dict was mutated"
        assert tool_input == before_input, "the incoming tool_input was mutated"
