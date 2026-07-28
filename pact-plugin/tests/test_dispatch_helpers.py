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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared.dispatch_helpers import is_owner_wiring_shape  # noqa: E402


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
