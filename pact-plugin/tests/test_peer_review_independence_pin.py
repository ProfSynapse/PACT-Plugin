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
    ("index", "the surface that arrives unsought — a reader who takes 'store' to "
              "mean the files concludes that opening none is safe"),
    ("compare", "the imperative; the nouns above survive a rewrite that drops it"),
    ("state", "the disclosure the orchestrator owes when the types match"),
    ("dispatch", "the action the different-type lever attaches to"),
    ("secretary", "the query a decisive cross-check must omit — `dispatch` and "
                  "`different` both survive this sentence's deletion, so the two "
                  "tokens nearest it cannot detect its loss"),
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


def test_the_clause_precedes_the_spawn_template():
    """An imperative about choosing `subagent_type` must sit where that choice
    is made. Placed after the dispatch procedure it contradicts its own section
    heading, which describes what happens once reviewers have reported.

    The clause pin above locates by anchor and is position-blind, so a move
    costs it nothing — which is why position needs its own assertion.
    """
    text = PEER_REVIEW.read_text(encoding="utf-8")
    anchor = text.find(ANCHOR)
    template = text.find("\nAgent(\n")
    assert anchor != -1 and template != -1, "anchor or spawn template missing"
    assert anchor < template, (
        "the REVIEWER-MEMORY-CHANNEL clause now sits AFTER the Agent( spawn "
        "template. The instruction tells the orchestrator to compare types "
        "before dispatching, so it belongs before the call that dispatches."
    )


def test_the_harvest_paragraph_points_at_the_clause():
    """The Working Memory paragraph describes a remedy that covers one surface.
    Left alone it reads as complete, which is the defect this clause exists to
    fix, so it must carry a cross-reference onward.

    Keyed on the anchor NAME occurring a second time rather than on the pointer's
    wording, so any rephrasing that still names the clause passes and only
    dropping the reference fails.
    """
    text = PEER_REVIEW.read_text(encoding="utf-8")
    assert text.count("REVIEWER-MEMORY-CHANNEL") >= 2, (
        "the harvest paragraph no longer points at the REVIEWER-MEMORY-CHANNEL "
        "clause, so a reader of it meets one channel and concludes that is the "
        "one to watch"
    )


def test_the_clause_extraction_stops_at_the_clause():
    """`_clause()` reads anchor-to-blank-line, so losing the blank line after
    the clause silently widens every token row above into the next step — the
    co-occurrence asserts would then pass on words that live elsewhere.

    Broken once while renumbering this list, and caught only by hand.
    """
    clause = _clause().rstrip()
    assert re.search(r"\s\d+\.\s", clause) is None, (
        "the clause extraction has run PAST the clause and swallowed a numbered "
        "step, so every token row above can now be satisfied by another "
        "instruction's words. Restore the blank line after the clause."
    )
    assert clause.endswith("."), (
        "the clause extraction is TRUNCATED — it stops mid-sentence, so the "
        "token rows above are searching only part of the clause. Look for a "
        "blank line introduced inside it."
    )
