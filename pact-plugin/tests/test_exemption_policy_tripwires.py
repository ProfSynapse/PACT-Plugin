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

WHAT IS DELIBERATELY NOT PINNED — the auditor's `metadata.type` state. The
denominator keys on `is_teachback_exempt`, which has no metadata surface, so
that fact is irrelevant here and pinning it would ossify a hazard that no
longer exists.
"""
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared import intentional_wait  # noqa: E402
from shared.intentional_wait import (  # noqa: E402
    SELF_COMPLETE_EXEMPT_AGENT_TYPES,
    TEACHBACK_EXEMPT_AGENT_TYPES,
    is_teachback_exempt,
)
from shared.variety_divergence import check_denominator_liveness  # noqa: E402

WRAPUP_PATH = Path(__file__).parent.parent / "commands" / "wrap-up.md"
VARIETY_PROTOCOL = Path(__file__).parent.parent / "protocols" / "pact-variety.md"


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


def _q5_line():
    for line in WRAPUP_PATH.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("5. **Variety divergence**"):
            return line
    raise AssertionError("Q5 question line not found in wrap-up.md")


class TestTheTwoExemptionSetsAreNotAliased:
    """The source comment says: "DO NOT recouple by ALIASING to the prior
    constant." Aliasing is an IDENTITY claim, so the test must be one.

    MUTATION THAT REDDENS: in `shared/intentional_wait.py`, replace the
    `TEACHBACK_EXEMPT_AGENT_TYPES = frozenset({...})` literal with
    `TEACHBACK_EXEMPT_AGENT_TYPES = SELF_COMPLETE_EXEMPT_AGENT_TYPES`.
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

    def test_a_content_check_could_not_have_caught_that(self):
        """NON-VACUITY, and the reason this file asserts identity at all.

        The two frozensets have IDENTICAL CONTENTS today, so every
        content-shaped form of this pin passes on an ALIASED pair and pins
        nothing. Simulate the forbidden recoupling and show each candidate
        predicate's verdict on it.
        """
        assert TEACHBACK_EXEMPT_AGENT_TYPES == SELF_COMPLETE_EXEMPT_AGENT_TYPES, (
            "precondition for this proof: contents are equal today"
        )

        aliased = SELF_COMPLETE_EXEMPT_AGENT_TYPES  # the forbidden `T = S`

        # Content form: BLIND -- passes on the aliased pair.
        assert aliased == SELF_COMPLETE_EXEMPT_AGENT_TYPES
        # Identity form: DETECTS -- this is the only discriminating check.
        assert aliased is SELF_COMPLETE_EXEMPT_AGENT_TYPES


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


class TestCheckAWitnessCannotSilentlyOmitTheExemptionSet:
    """Consumer (b): Check A's witness filter.

    `check_denominator_liveness` does NOT read the SSOT -- it takes the
    exemption set as a parameter, threaded by the caller. That is the better
    design for an LLM-executed caller, and this pin is what keeps it true:
    with NO DEFAULT, omitting the argument is a loud TypeError and the
    constant must appear BY NAME in reviewable instruction text. Add a
    default and the markdown can quietly stop naming it while everything
    still runs -- a silent coupling whose rot is undetectable.

    SCOPE, stated because this pin must not inherit a claim it does not
    make: no-default catches OMISSION -- the argument being dropped. It does
    NOT catch DIVERGENCE, where a caller passes the set's CONTENTS inlined
    instead of the constant. That passes here, works today, and silently
    decouples the witness from the SSOT, so a later addition to
    TEACHBACK_EXEMPT_AGENT_TYPES would reach the emit predicate and not the
    witness. Divergence is covered separately by
    `test_q5_does_not_inline_the_exempt_set_contents`. Neither pin is
    sufficient alone.

    MUTATION THAT REDDENS: give `exempt_types` any default value, e.g.
    `exempt_types: frozenset = frozenset()`.
    """

    def test_exempt_types_has_no_default(self):
        param = inspect.signature(check_denominator_liveness).parameters[
            "exempt_types"
        ]
        assert param.default is inspect.Parameter.empty, (
            "check_denominator_liveness.exempt_types has acquired a default. "
            "The caller is LLM-executed markdown: with no default, dropping "
            "the argument fails loudly and the SSOT constant must be named in "
            "the instruction text. With a default, the instruction can stop "
            "naming it and the witness silently filters on a different set "
            "than the denominator excludes."
        )

    def test_omitting_the_exemption_set_is_a_loud_failure(self):
        """Non-vacuity for the above: prove the no-default state actually
        produces the loud failure the pin claims it does."""
        with pytest.raises(TypeError):
            check_denominator_liveness([], [], [])


class TestQ5ThreadsTheExemptionConstantIntoCheckA:
    """Consumer (b), instruction half: the Q5 text must invoke the helper AND
    thread the SSOT constant by name, rather than writing an exempt set out
    locally. A second copy of that set is how the witness and the denominator
    drift apart.

    SCOPE LIMIT, stated because it is easy to overread: this pins the
    INSTRUCTION, not the runtime. wrap-up.md is executed by an LLM, so a red
    here means the instruction changed; a green does not prove the constant
    was threaded at run time.

    MUTATION THAT REDDENS: edit Q5 to inline a set literal in the call, e.g.
    `check_denominator_liveness(events, dd, skips, frozenset({"pact-secretary"}))`.
    """

    def test_q5_calls_check_a_threading_the_named_constant(self):
        q5 = _q5_line()
        assert "check_denominator_liveness" in q5
        assert "TEACHBACK_EXEMPT_AGENT_TYPES" in q5, (
            "Q5 no longer names TEACHBACK_EXEMPT_AGENT_TYPES. Check A's "
            "witness must exclude exactly what the denominator excludes; a "
            "locally-written exempt set is a second copy that will drift."
        )
        call_start = q5.find("check_denominator_liveness(")
        assert call_start != -1, "the helper is named but never called"
        call_text = q5[call_start:call_start + 200]
        assert "TEACHBACK_EXEMPT_AGENT_TYPES" in call_text, (
            "the constant is named somewhere in Q5 but is not threaded "
            "THROUGH THE CALL -- naming it in prose while passing something "
            "else is exactly the drift this pin exists to catch"
        )

    def test_q5_does_not_inline_the_exempt_set_contents(self):
        """The DIVERGENCE half, which the no-default pin does not cover.

        Someone "simplifying" the instruction can inline the set's contents
        instead of importing the constant. That passes every other pin here
        and works today -- and silently decouples Check A's witness from the
        SSOT, so a later addition to TEACHBACK_EXEMPT_AGENT_TYPES reaches the
        emit predicate and NOT the witness.

        The forbidden literals are DERIVED FROM THE CONSTANT rather than
        hard-coded, which buys three things: it discriminates today, it
        auto-tracks the set as it grows instead of freezing today's contents,
        and its red means exactly one thing -- the contents were inlined
        instead of the name.

        NOT a `pact-` prefix probe, deliberately: Q5 legitimately contains
        `pact-variety` (a documentation filename), so a prefix-keyed pin is
        RED ON CORRECT CODE -- the mirror of the vacuity failure -- and
        would force a hand-maintained exclusion list that rots.

        NEITHER THIS PIN NOR `test_q5_calls_check_a_threading_the_named_constant`
        SUBSUMES THE OTHER -- do not delete one as redundant. They overlap on
        the obvious mutation and diverge on the interesting ones, and both
        directions were demonstrated:

          * pass a DIFFERENT VARIABLE in the call (`..., exempt)`) --
            the call-text pin REDS, this one stays green: no member literal
            is present anywhere.
          * leave the constant threaded and write a SECOND COPY of the
            contents into nearby prose -- this pin REDS, the call-text pin
            stays green: the call itself is still correct.

        The call-text pin guards the CALL SITE; this one guards the WHOLE
        SECTION against a second copy of the set appearing at all.

        MUTATION THAT REDDENS: replace the threaded constant in the Q5 call
        with `frozenset({"pact-secretary"})` -- which reddens BOTH pins, and
        is exactly why the two asymmetric mutations above are the ones that
        establish independence.
        """
        q5 = _q5_line()
        for member in sorted(TEACHBACK_EXEMPT_AGENT_TYPES):
            for literal in (f'"{member}"', f"'{member}'"):
                assert literal not in q5, (
                    f"Q5 inlines the exempt-set member {literal} instead of "
                    "threading TEACHBACK_EXEMPT_AGENT_TYPES. A copy of the "
                    "set's contents does not track the set: add an agent "
                    "type later and the emit predicate excludes it while "
                    "Check A's witness still counts it, which is the drift "
                    "this pin exists to catch."
                )


class TestProtocolProseNamesTheSameConstant:
    """Consumer (c): the protocol prose.

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
