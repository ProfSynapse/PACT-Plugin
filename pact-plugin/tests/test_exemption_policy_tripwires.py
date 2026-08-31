"""
Executable tripwires over the Q5 EXEMPTION POLICY.

The denominator is now hook-emitted and therefore author-proof: no command
file can move it by writing prose. What CAN still move it is the exemption
sets — they decide which dispatches are sites at all. This file converts the
prose rules guarding them into assertions that can fail.

Each pin below names, in its own docstring, the MUTATION that reddens it. A
pin whose mutation cannot be named is not a pin; it is coverage-shaped
decoration, and this file exists because that failure has already shipped
twice in this area.

NOT PINNED FOR THE DENOMINATOR — the auditor's `metadata.type` state. The
denominator keys on `is_teachback_exempt`, which has no metadata surface, so
that fact is irrelevant to it. It IS pinned lower down for a different
consumer: the harvest predicate's state set depends on auditors staying
non-exempt, which depends on that dispatch carrying no `type`.
"""
import ast
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared import intentional_wait  # noqa: E402
from shared.intentional_wait import (  # noqa: E402
    SELF_COMPLETE_EXEMPT_AGENT_TYPES,
    TEACHBACK_EXEMPT_AGENT_TYPES,
    is_self_complete_exempt,
    is_teachback_exempt,
)

VARIETY_PROTOCOL = Path(__file__).parent.parent / "protocols" / "pact-variety.md"
INTENTIONAL_WAIT_SRC = (
    Path(__file__).parent.parent / "hooks" / "shared" / "intentional_wait.py"
)


def _assigned_value_node(source, target_name):
    """Return the AST value node assigned to a module-level `target_name`.

    Handles both `X = ...` and the annotated `X: frozenset = ...` form.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == target_name:
                return node.value
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target_name:
                    return node.value
    raise AssertionError(
        f"no module-level assignment to {target_name!r} found -- the constant "
        f"was renamed or moved, which this file's pins depend on"
    )


def _write_team_config(teams_dir, team_name, members):
    team_dir = Path(teams_dir) / team_name
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / "config.json").write_text(
        json.dumps({"team_name": team_name, "members": members}),
        encoding="utf-8",
    )
    return str(teams_dir)


@pytest.fixture
def teams_dir(tmp_path):
    d = tmp_path / "teams"
    d.mkdir()
    return str(d)


class TestTheTwoExemptionSetsAreNotAliased:
    """The source comment says: "DO NOT recouple by ALIASING to the prior
    constant." Aliasing is an IDENTITY claim, so the test must be one.

    MUTATION THAT REDDENS: in `shared/intentional_wait.py`, replace the
    `TEACHBACK_EXEMPT_AGENT_TYPES = frozenset({...})` literal with
    `TEACHBACK_EXEMPT_AGENT_TYPES = SELF_COMPLETE_EXEMPT_AGENT_TYPES`.

    WHY IDENTITY AND NOT CONTENTS. The two frozensets hold identical
    contents today, so a content-shaped pin (`T == S`, or comparing either
    against a literal) stays GREEN on an aliased pair and detects nothing.
    `is not` is the only form that separates "two sets that happen to
    match" from "one set under two names".

    AND WHY NOT A PIN ON THE CONTENTS BEING EQUAL TODAY. That would redden
    on a change the module explicitly invites -- its docstring supports
    future divergence, a rote-only agentType joining one set with a one-line
    change. A test that fires on an intended edit is worse than no test, so
    the content relationship is recorded in this paragraph and asserted
    nowhere. A previous test did assert it, by binding a local alias and
    comparing that local against the constant it had just been assigned
    from; both arms were true by the assignment and no change to this module
    could redden either. Do not re-add that shape.

    TWO PINS, TWO DIFFERENT OBSERVATIONS -- neither subsumes the other:
    - `test_the_two_sets_are_distinct_objects` reads the IMPORTED objects
      and catches `T = S`.
    - `test_the_teachback_set_is_not_derived_from_the_self_complete_set`
      reads the SOURCE and additionally catches `T = frozenset({*S})`,
      which the identity pin cannot see.
    """

    def test_the_two_sets_are_distinct_objects(self):
        assert TEACHBACK_EXEMPT_AGENT_TYPES is not SELF_COMPLETE_EXEMPT_AGENT_TYPES, (
            "TEACHBACK_EXEMPT_AGENT_TYPES has been ALIASED to "
            "SELF_COMPLETE_EXEMPT_AGENT_TYPES. These are two policy surfaces "
            "answering different questions -- 'should this owner be dispatched "
            "through a teachback gate?' vs 'may this owner self-complete?' -- "
            "and aliasing them means a future change to either silently moves "
            "the other, including the Q5 denominator."
        )

    def test_the_teachback_set_is_not_derived_from_the_self_complete_set(self):
        """The coupling the identity pin above CANNOT see.

        `is not` compares objects, so it catches `T = S` and nothing else.
        It passes on `T = frozenset({*S})` and `T = frozenset(set(S))`,
        which build a DISTINCT object whose contents are still DERIVED from
        S -- measured, not assumed: `frozenset({*S}) is S` is False while
        `frozenset({*S}) == S` is True. That is the plausible shape of a
        well-meant decoupling that decouples nothing: it satisfies the
        identity pin while leaving a later edit to S silently moving T, and
        with it the Q5 denominator.

        Reads the SHIPPED SOURCE rather than the imported values because the
        forbidden thing is a source relationship. By the time the module is
        imported, `frozenset({*S})` has already collapsed into an ordinary
        frozenset carrying no trace of where its members came from -- the
        evidence exists only in the assignment expression.

        Deliberately narrow: it forbids REFERENCING the other constant, not
        every non-literal form. `T = frozenset(_ROTE_AGENT_TYPES)` off some
        independent source stays green, because that is a real decoupling.

        MUTATIONS THAT REDDEN: `TEACHBACK_EXEMPT_AGENT_TYPES =
        SELF_COMPLETE_EXEMPT_AGENT_TYPES` (also caught by the pin above), or
        `= frozenset({*SELF_COMPLETE_EXEMPT_AGENT_TYPES})` (caught ONLY
        here).
        """
        value = _assigned_value_node(
            INTENTIONAL_WAIT_SRC.read_text(encoding="utf-8"),
            "TEACHBACK_EXEMPT_AGENT_TYPES",
        )
        referenced = {
            n.id for n in ast.walk(value) if isinstance(n, ast.Name)
        }
        assert "SELF_COMPLETE_EXEMPT_AGENT_TYPES" not in referenced, (
            "TEACHBACK_EXEMPT_AGENT_TYPES is now DERIVED from "
            "SELF_COMPLETE_EXEMPT_AGENT_TYPES in the source. Even when the "
            "two are distinct objects -- so the identity pin stays green -- "
            "deriving one from the other recouples them: editing the "
            "self-complete carve-out silently moves the teachback carve-out, "
            "and with it which dispatches count as Q5 sites. Build the set "
            "from its own literal, or from a source that is not the other "
            "policy surface."
        )


class TestAuditorDispatchesCount:
    """A `pact-auditor` owner is NOT teachback-exempt, so auditor dispatches
    are dispatch SITES and land in the Q5 denominator.

    MUTATION THAT REDDENS: add `"pact-auditor"` to
    TEACHBACK_EXEMPT_AGENT_TYPES.
    """

    def test_pact_auditor_is_not_teachback_exempt(self):
        assert "pact-auditor" not in TEACHBACK_EXEMPT_AGENT_TYPES, (
            "pact-auditor has been added to TEACHBACK_EXEMPT_AGENT_TYPES, "
            "which REMOVES every auditor dispatch from the Q5 coverage "
            "denominator. Auditor dispatches COUNT: an un-stamped auditor "
            "dispatch is a genuine coverage gap whose remedy is stamping it, "
            "never exempting it so the number improves."
        )

    def test_an_auditor_owner_resolves_as_non_exempt_end_to_end(self, teams_dir):
        """The set-membership assertion above is about the constant; this one
        drives the real predicate over a real team config, so it also covers
        the resolution path the denominator actually calls."""
        _write_team_config(teams_dir, "t", [
            {"name": "auditor", "agentType": "pact-auditor"},
        ])
        assert is_teachback_exempt("auditor", "t", teams_dir) is False


class TestTheEmitPredicateReadsTheSSOT:
    """Consumer (a): the emit predicate resolves exemption through
    TEACHBACK_EXEMPT_AGENT_TYPES and no other set.

    This is BEHAVIOURAL rather than an import/AST check on purpose: an
    import proves the name is in scope, not that the decision consults it.

    MUTATION THAT REDDENS: in `_is_teachback_exempt_agent_type`, change
    `agent_type in TEACHBACK_EXEMPT_AGENT_TYPES` to
    `agent_type in SELF_COMPLETE_EXEMPT_AGENT_TYPES`. The monkeypatch below
    then stops changing the verdict.
    """

    def test_predicate_verdict_follows_the_teachback_constant(
        self, teams_dir, monkeypatch
    ):
        _write_team_config(teams_dir, "t", [
            {"name": "someone", "agentType": "pact-auditor"},
        ])
        # Baseline: not exempt, because pact-auditor is not in the SSOT.
        assert is_teachback_exempt("someone", "t", teams_dir) is False

        # Move ONLY the teachback SSOT; the verdict must follow it.
        monkeypatch.setattr(
            intentional_wait,
            "TEACHBACK_EXEMPT_AGENT_TYPES",
            frozenset({"pact-auditor"}),
        )
        assert is_teachback_exempt("someone", "t", teams_dir) is True, (
            "the emit predicate's verdict did not follow "
            "TEACHBACK_EXEMPT_AGENT_TYPES, so it is resolving exemption "
            "through some other set -- the denominator and its policy have "
            "drifted apart"
        )


class TestProtocolProseNamesTheSameConstant:
    """Consumer (b): the protocol prose.

    HONEST SCOPE, and it must not be reported as more than this: prose cannot
    READ an SSOT, so this checks only that it NAMES the same constant. A red
    here means SOMEONE REWORDED THE PROSE -- it does NOT mean the consumers
    drifted. It is included because a protocol that names a symbol which no
    longer exists is its own defect, not because it verifies the coupling.

    MUTATION THAT REDDENS: rename the constant in the protocol prose, or
    remove the sentence naming it.
    """

    def test_variety_protocol_names_the_exemption_constant(self):
        text = VARIETY_PROTOCOL.read_text(encoding="utf-8")
        assert "TEACHBACK_EXEMPT_AGENT_TYPES" in text, (
            "the Q5 denominator protocol no longer names "
            "TEACHBACK_EXEMPT_AGENT_TYPES -- the category justification rests "
            "on that constant being a pre-existing declaration, so a doc that "
            "stops naming it loses the independent ground the ruling needs"
        )


# Grep target for anyone editing the claim gate: task_claim_gate._atomic_claim
# writes the second of these states. If it learns a third, this set is what the
# harvest predicate in agents/pact-orchestrator.md must grow to cover.
ATOMIC_CLAIM_LIVE_STATES = frozenset({"pending", "in_progress"})

ORCHESTRATOR_PERSONA = Path(__file__).parent.parent / "agents" / "pact-orchestrator.md"
AUDITOR_DISPATCH_SITES = (
    Path(__file__).parent.parent / "commands" / "orchestrate.md",
    Path(__file__).parent.parent / "commands" / "comPACT.md",
)


class TestAuditorLivenessPredicateCoversTheClaimGate:
    """The harvest predicate names task states; its state set is correct only
    because of facts in two files it never references. These arms carry that
    coupling.

    NOT COVERED, stated rather than implied: a rewording that keeps both state
    tokens and inverts their sense ("`pending`, never `in_progress`") passes the
    token-set arm. Pinning sentence structure instead would redden on every
    legitimate rewrite, which is the trade taken here deliberately.
    """

    def test_harvest_predicate_names_every_state_the_claim_gate_can_produce(self):
        """Reddens on BOTH states this predicate shipped in one PR:
        `in_progress`-only and `pending`-only. Asserts the anchor exists first,
        so deleting the line fails loudly instead of passing vacuously."""
        lines = [
            ln for ln in ORCHESTRATOR_PERSONA.read_text().splitlines()
            if "no auditor task is" in ln
        ]
        assert len(lines) == 2, "harvest predicate anchor missing or moved: %r" % (lines,)
        for ln in lines:
            # states are named in the CONDITION; the trailing `(workflow)` is not one
            condition = ln.split("\u2192")[0]
            assert set(re.findall(r"`(\w+)`", condition)) == ATOMIC_CLAIM_LIVE_STATES, ln

    def test_auditor_shaped_task_is_not_self_complete_exempt(self):
        """The fact the predicate rests on. Reddens if either exemption surface
        starts admitting auditors — the dependency editor's tripwire."""
        assert "pact-auditor" not in SELF_COMPLETE_EXEMPT_AGENT_TYPES
        assert is_self_complete_exempt(
            {"owner": "auditor", "metadata": {"completion_type": "signal"}}, ""
        ) is False

    def test_no_auditor_dispatch_site_sets_metadata_type(self):
        """Reddens if a dispatch gains `metadata.type`, which would make
        auditors exempt, keep them out of `in_progress`, and silently un-couple
        the predicate. The prose already forbids this; this is its enforcement."""
        found = 0
        for path in AUDITOR_DISPATCH_SITES:
            for m in re.finditer(
                r'metadata(?:=|: )(\{[^}]*"completion_type"[^}]*\})', path.read_text()
            ):
                found += 1
                assert set(json.loads(m.group(1))) == {"completion_type"}, (
                    path.name, m.group(1)
                )
        assert found >= 2, "auditor dispatch metadata literals not found: %d" % found
