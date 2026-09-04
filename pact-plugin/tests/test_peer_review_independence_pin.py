"""Structural pin for the reviewer-independence channels in commands/peer-review.md.

The file protects reviewer independence in prose and names TWO channels with
DIFFERENT remedies. The Working Memory block is pushed into live agents
mid-session, so ordering the harvest after the reviewers is a real fix.
Persistent agent-memory is keyed by agent TYPE and loaded at spawn, so no
ordering reaches it and the remedy is a type comparison instead. A reader who
meets only the first concludes the covered channel is the one to watch, which
is why the second sits beside it rather than elsewhere.

Keyed on a stable anchor plus token co-occurrence inside that clause, following
test_peer_review_greedy_pin.py: benign rewording survives, dropping a
load-bearing clause fails.

CEILING: this cannot see advice reworded into uselessness while every token
survives. It catches deletion of the clause and loss of any of its four
load-bearing parts — the key, the mechanism, the disclosure and the lever.
"""
import re
from pathlib import Path

import pytest

PEER_REVIEW = Path(__file__).parent.parent / "commands" / "peer-review.md"
ANCHOR = "ANCHOR-STABLE: REVIEWER-MEMORY-CHANNEL"


def _clause() -> str:
    """The agent-memory clause alone, so a token living elsewhere in the file
    cannot satisfy the co-occurrence asserts below."""
    text = PEER_REVIEW.read_text(encoding="utf-8")
    start = text.find(ANCHOR)
    assert start != -1, f"peer-review.md lost the {ANCHOR} clause"
    end = text.find("\n\n", start)
    return re.sub(r"\s+", " ", text[start:end if end != -1 else None].lower())


@pytest.mark.parametrize("token, lost", [
    ("subagent_type", "the key the comparison is made on"),
    ("agent-memory", "the channel being named"),
    ("spawn", "why ordering cannot fix it"),
    ("different", "the lever that buys independence"),
])
def test_clause_keeps_its_load_bearing_parts(token, lost):
    assert token in _clause(), (
        f"the reviewer-independence clause no longer names {token!r} — {lost}. "
        f"Without it an orchestrator spawning a fresh agent concludes it is "
        f"independent."
    )


def test_the_clause_states_the_limitation_rather_than_blocking():
    """Same-type review is normally correct — this file's own selection table
    picks the type that just wrote the code. The instruction must remain a
    disclosure, not a gate."""
    clause = _clause()
    assert "state" in clause or "record" in clause, (
        "the clause no longer tells the orchestrator to state the limitation"
    )
    for forbidden in ("must not spawn", "refuse", "block"):
        assert forbidden not in clause, (
            f"the clause now {forbidden!r}s same-type review, which breaks the "
            f"standard flow this file's selection table prescribes"
        )
