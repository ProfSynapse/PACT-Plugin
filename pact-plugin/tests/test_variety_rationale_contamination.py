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
_PLACEHOLDER = re.compile(r"why this score for THIS dispatch's (?:novelty|scope|uncertainty|risk)>")

_RULE = "Do not write the dispatch's hypothesis, its expected answer, or the reasoning that produced it."


def _surfaces():
    return sorted(PLUGIN.glob("commands/*.md")) + [VARIETY, PROTOCOLS]


def test_no_bare_rationale_placeholder_survives():
    """Every writer-side placeholder carries the constraint inline.

    A bare placeholder is one a lead reads while composing without being told
    what must not go in it.
    """
    bare = {
        p.relative_to(PLUGIN).as_posix(): len(_PLACEHOLDER.findall(p.read_text(encoding="utf-8")))
        for p in _surfaces()
    }
    offenders = {k: v for k, v in bare.items() if v}
    assert not offenders, f"bare rationale placeholders: {offenders}"


def test_constraint_reaches_the_writer():
    """Non-vacuity: the population is non-empty and does carry placeholders.

    Without this, the arm above passes on a glob that matches nothing.
    """
    suffixed = sum(
        t.count("shape only, not the hypothesis")
        for t in (p.read_text(encoding="utf-8") for p in _surfaces())
    )
    assert suffixed >= 20, f"expected the placeholder population, found {suffixed}"


def test_schema_block_states_the_rule_in_both_mirror_halves():
    """The clause a placeholder suffix cannot carry, in the SSOT and its mirror."""
    for path in (VARIETY, PROTOCOLS):
        text = path.read_text(encoding="utf-8")
        assert _RULE in text, f"{path.name}: rule absent"
        assert "must not disclose it" in text, f"{path.name}: not-knowing clause absent"
