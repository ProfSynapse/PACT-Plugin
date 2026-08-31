"""The harvest dispatch sites and the prose describing them must desync together.

The dispatch sites in ``commands/`` are the ground truth: each one tells the
secretary to follow a named harvest workflow, so the pair (command, variant) is
a fact about what the repository does. The orchestrator persona's trigger list
and the harvest skill's variant list are CLAIMS about those pairs. This module
asserts the claims equal the facts, in both directions, so adding a dispatch
without listing it and listing a trigger with no dispatch each redden.

BOUND, stated because it is narrower than the assertion looks: the multiset
counts dispatch sites, it does not identify them. Two distinct boundaries and
one boundary dispatched twice are the same count, so the gate reddens on the
second and the fix is to enumerate it — which is the right outcome either way.
A dispatch site carrying no ``Follow the <Variant> Harvest workflow`` string is
invisible here; give a new one that string or this gate cannot see it.

EXTRACTION RULE, stated because an under-matching extractor yields a green that
proves nothing and every local step of building it looks correct:

  * ground truth -- every ``Follow the <Variant> Harvest workflow`` in a
    ``commands/*.md``, paired with that file's stem. Several dispatch sites may
    yield the same pair, and THE TWO SURFACES COUNT THEM DIFFERENTLY because
    they claim different things. The persona enumerates BOUNDARIES, one row
    each, so it compares as a MULTISET: two boundaries in one command are two
    rows. The skill maps a variant to the commands that use it, so it compares
    as a SET: naming a command twice there would be wrong. A single unit for
    both surfaces is what let a second dispatch site hide.
  * persona -- every line of the Memory Processing Triggers block naming a
    variant with an arrow AND a backticked command.
  * skill -- every variant bullet's parenthesised comma list of commands.

Extraction reads whole file text, never line by line: a dispatch ``description=``
string spans many lines, so a line-oriented scan sees fragments of it.

Each source is asserted NON-EMPTY before the sets are compared. Two empty sets
are equal, so a comparison over a failed extraction would pass while measuring
nothing.

WHAT THIS DOES NOT CATCH: whether a dispatch fires at the workflow boundary its
prose claims. The pair is (command, variant); the boundary within the command is
prose with no machine-readable counterpart, so moving a harvest earlier or later
inside the same command changes nothing here.
"""

import re
from collections import Counter
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent
COMMANDS = PLUGIN / "commands"
PERSONA = PLUGIN / "agents" / "pact-orchestrator.md"
SKILL = PLUGIN / "skills" / "pact-handoff-harvest" / "SKILL.md"

_DISPATCH = re.compile(r"Follow the (\w+) Harvest workflow")
_PERSONA_ROW = re.compile(r"→\s*(\w+) Harvest.*?`([\w-]+)`")
_SKILL_BULLET = re.compile(r"\*\*(\w+) Harvest\*\*[^\n]*?\(([^)]*)\)")


def _dispatched():
    """(command stem, variant) for every harvest dispatch under commands/.

    A LIST, so a command dispatching one variant at two boundaries yields two
    entries. The persona compares as a MULTISET and the skill as a SET; see
    the per-surface unit in the parametrize below.
    """
    return [
        (path.stem, variant)
        for path in sorted(COMMANDS.glob("*.md"))
        for variant in _DISPATCH.findall(path.read_text(encoding="utf-8"))
    ]


def _persona_claims():
    """(command, variant) claimed by the orchestrator's trigger rows."""
    return [
        (command, variant)
        for variant, command in _PERSONA_ROW.findall(
            PERSONA.read_text(encoding="utf-8")
        )
    ]


def _skill_claims():
    """(command, variant) claimed by the harvest skill's variant bullets."""
    return [
        (command.strip(), variant)
        for variant, commands in _SKILL_BULLET.findall(
            SKILL.read_text(encoding="utf-8")
        )
        for command in commands.split(",")
    ]


def _excess(a, b):
    """Members of `a` not covered by `b`, preserving multiplicity for Counters."""
    diff = a - b
    return sorted(diff.elements() if isinstance(diff, Counter) else diff)


class TestHarvestTriggersAgreeAcrossSurfaces:
    """Dispatch sites are the oracle; both prose enumerations must match them."""

    @pytest.mark.parametrize(
        "name,claims,unit",
        [
            ("orchestrator persona", _persona_claims, Counter),
            ("harvest skill", _skill_claims, set),
        ],
    )
    def test_prose_enumeration_matches_the_dispatch_sites(self, name, claims, unit):
        dispatched = unit(_dispatched())
        assert dispatched, (
            f"no `Follow the <Variant> Harvest workflow` dispatch found under "
            f"{COMMANDS}. The oracle is empty, so the comparison below would "
            f"hold vacuously. Report this as an extraction failure, not as "
            f"agreement."
        )
        claimed = unit(claims())
        assert claimed, (
            f"the {name} surface yielded NO (command, variant) pairs. Either "
            f"the surface stopped enumerating them or the extraction rule in "
            f"this module's docstring no longer matches how it states them. "
            f"Report this as an extraction failure, not as agreement."
        )
        assert claimed == dispatched, (
            f"THE {name.upper()} AND THE DISPATCH SITES DISAGREE.\n"
            f"  dispatched but not claimed: {_excess(dispatched, claimed)}\n"
            f"  claimed but not dispatched: {_excess(claimed, dispatched)}\n"
            f"A dispatch tells the secretary to run a named workflow, so every "
            f"dispatched pair belongs in this surface and every pair it names "
            f"must have a dispatch. Update whichever side you did not just edit."
        )
