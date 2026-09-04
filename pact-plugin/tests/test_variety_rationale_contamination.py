"""
Location: pact-plugin/tests/test_variety_rationale_contamination.py

Variety rationales are read by a teammate BEFORE it starts work, so a rationale
carrying the dispatch's hypothesis hands a seat the thing it may exist not to
know. These arms pin the constraint at both places it has to hold: the
placeholder a lead fills in, and the schema block that defines it.

POPULATION, not a fixed list: the placeholder arm walks every `commands/*.md`
and both protocol files, so a template added later is covered on the day it
arrives rather than when someone remembers this file.
"""

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
VARIETY = PLUGIN / "protocols" / "pact-variety.md"
PROTOCOLS = PLUGIN / "protocols" / "pact-protocols.md"

# A placeholder a lead fills in. The suffix is the constraint; a bare one is the defect.
_PLACEHOLDER = re.compile(r"why this score for THIS dispatch's (?:novelty|scope|uncertainty|risk)")

_RULE = "Do not write the dispatch's hypothesis, its expected answer, or the reasoning that produced it."


def _surfaces():
    return sorted(PLUGIN.glob("commands/*.md")) + [VARIETY, PROTOCOLS]


def test_no_bare_rationale_placeholder_survives():
    """Every writer-side placeholder carries the constraint inline.

    "why this score" solicits causal reasoning, and the honest causal answer is
    often the belief itself — so the prompt must not ask it at all.
    """
    bare = {
        p.relative_to(PLUGIN).as_posix(): len(_PLACEHOLDER.findall(p.read_text(encoding="utf-8")))
        for p in _surfaces()
    }
    offenders = {k: v for k, v in bare.items() if v}
    assert not offenders, f"causal-prompt rationale placeholders: {offenders}"


def test_constraint_reaches_the_writer():
    """Non-vacuity: the population is non-empty and does carry placeholders.

    Without this, the arm above passes on a glob that matches nothing.

    THE FLOOR IS ARBITRARY HEADROOM, NOT A DERIVED COUNT. Its only job is to
    prove the glob is live. It is deliberately far below the real population
    so that legitimately removing a template or consolidating a dispatch block
    does not redden it — this file pins that no placeholder solicits causal
    reasoning, not how many placeholders exist. Do not tighten it to track the
    census: a count that carries no meaning teaches the next reader that it
    does.
    """
    suffixed = sum(
        t.count("never what you expect to find")
        for t in (p.read_text(encoding="utf-8") for p in _surfaces())
    )
    assert suffixed >= 20, f"expected the placeholder population, found {suffixed}"


def test_schema_block_states_the_rule_in_both_mirror_halves():
    """The clause a placeholder suffix cannot carry, in the SSOT and its mirror."""
    for path in (VARIETY, PROTOCOLS):
        text = path.read_text(encoding="utf-8")
        assert _RULE in text, f"{path.name}: rule absent"
        assert "must not disclose it" in text, f"{path.name}: not-knowing clause absent"

TEACHBACK_SKILL = PLUGIN / "skills" / "pact-teachback" / "SKILL.md"

# The three surfaces that state when a teammate may read the rationales.
_ORDERING_SITES = (VARIETY, PROTOCOLS, TEACHBACK_SKILL)


def test_all_three_surfaces_state_the_same_read_ordering():
    """The split read is stated at three sites; two of three is worse than none.

    WHAT THIS CANNOT DO, and it is the point of the arm rather than a caveat:
    it cannot check that a teammate OBEYS the ordering. That happens at runtime
    in another agent. A phrase pin passes on a violated ordering. What it does
    check is the failure this change could actually introduce — one surface
    updated and another left stating the old rule.
    """
    for path in _ORDERING_SITES:
        text = path.read_text(encoding="utf-8")
        assert "ONLY AFTER" in text, f"{path.name}: read-ordering clause absent"
        assert "cannot be un-read" in text, f"{path.name}: required-not-preferred force absent"

def test_ignorance_dependent_seats_are_not_asked_for_acknowledgment():
    """The carve-out that closes the founding case, in both mirror halves.

    The split read alone does not close it: a teammate reading rationales
    after composing its understanding has still read them before the WORK.
    For a seat whose value is not knowing, the field is omitted entirely.
    """
    for path in (VARIETY, PROTOCOLS):
        text = path.read_text(encoding="utf-8")
        assert "do not ask that seat for `variety_acknowledgment`" in text, (
            f"{path.name}: omission carve-out absent"
        )
