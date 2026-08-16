"""Structural prose-surface regression guard for the CLAUDE.md write prohibition.

A teammate must not write a ``CLAUDE.md`` file in a project directory or a home
directory. The rule lives only in prose, in the pact-agent-teams skill body,
and the worktree boundary check allow-lists ``CLAUDE.md``, so no mechanical
control stands behind it. A later edit can narrow it back with nothing red.

THE NARROWING THIS GUARDS. The rule first said "do not edit or create". That
wording names a tool call the teammate ISSUES. It does not reach a write the
teammate CAUSES through a script, a command, or a save path it invokes, and
that indirect route is the one that produced the write. So the load-bearing
property is the ROUTE CLASS, not the presence of the rule: an edit that keeps
the prohibition and drops the route class re-opens the hole.

SLICE RULE, stated beside the assertions that use it: the guarded region is the
blockquote paragraph that opens with the bold marker
``**CLAUDE.md is not yours to write**`` and runs to the next blank line. The
slice is paragraph-bounded rather than file-bounded, so a route token sitting
in some unrelated part of the skill cannot satisfy these arms.

Keyed on structural tokens (semantic co-occurrence), not on exact prose, so
benign rewording survives and a narrowing fails.

  W1 — the prohibition paragraph is present and addresses the teammate.
  W2 — the paragraph carries the ROUTE CLASS: it says the rule is not limited
       to a directly-issued tool call, and it names indirect routes.
  W3 — the paragraph keeps its two bounds (target and role) and stays
       unconditional, so it does not slide back behind a worktree condition.

POPULATION NOT COVERED, recorded so the negative is readable: five dispatch
templates emit their own copy of this prohibition into a task description
(commands/orchestrate.md, commands/comPACT.md at two sites,
commands/peer-review.md, commands/rePACT.md). Those copies still carry the
narrow edit-or-create wording. They are outside this guard on purpose: arming
them here would assert a property the tree does not have yet.
"""
import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
AGENT_TEAMS_SKILL = PLUGIN_ROOT / "skills" / "pact-agent-teams" / "SKILL.md"

BLOCK_MARKER = "**CLAUDE.md is not yours to write**"

# Indirect routes the widened rule must name. Two of these must appear, so
# dropping one phrasing in a reword survives and dropping the CLASS fails.
INDIRECT_ROUTE_TOKENS = ("script", "command you invoke", "save path")
INDIRECT_ROUTE_FLOOR = 2


def _norm(text: str) -> str:
    """Lowercase + collapse whitespace so token checks survive line-wrapping."""
    return re.sub(r"\s+", " ", text.lower())


@pytest.fixture(scope="module")
def block() -> str:
    """The normalized prohibition paragraph, per the slice rule in the module
    docstring. Fails loudly when the marker is gone, so a renamed heading is a
    red arm rather than a silently empty slice."""
    text = AGENT_TEAMS_SKILL.read_text(encoding="utf-8")
    idx = text.find(BLOCK_MARKER)
    assert idx != -1, (
        f"{AGENT_TEAMS_SKILL.name} no longer carries the prohibition marker "
        f"{BLOCK_MARKER!r}. Either the rule was removed or its marker was "
        f"renamed; both leave every arm in this file measuring nothing."
    )
    end = text.find("\n\n", idx)
    paragraph = text[idx:] if end == -1 else text[idx:end]
    assert paragraph.strip(), "prohibition paragraph sliced empty"
    return _norm(paragraph)


class TestW1ProhibitionPresent:
    """The rule is present and addresses the teammate."""

    def test_addresses_the_teammate(self, block):
        assert "as a teammate" in block, (
            "prohibition no longer addresses the teammate role; the role bound "
            "is what keeps the orchestrator and the secretary outside the rule"
        )

    def test_forbids_the_write(self, block):
        assert re.search(r"do not write a `?claude\.md`? file", block), (
            "prohibition no longer forbids WRITING the file"
        )


class TestW2RouteClass:
    """The widened class: the rule covers a write the teammate CAUSES, not only
    a tool call it ISSUES. This is the arm that reddens on a narrowing edit."""

    def test_states_the_rule_is_not_limited_to_a_direct_tool_call(self, block):
        # The coupling is "not only" bound to a tool name, inside this
        # paragraph. A revert to "do not edit or create ..." drops it.
        assert re.search(r"not only an?\s+`?(edit|write)`?", block), (
            "prohibition lost the clause saying the rule is NOT limited to an "
            "Edit or a Write the teammate issues. Without it the sentence "
            "names an editing ACT, and a write caused through a script or a "
            "save path reads as out of scope."
        )

    def test_names_indirect_routes(self, block):
        found = [t for t in INDIRECT_ROUTE_TOKENS if t in block]
        assert len(found) >= INDIRECT_ROUTE_FLOOR, (
            f"prohibition names only {len(found)} indirect route(s) {found}; "
            f"floor is {INDIRECT_ROUTE_FLOOR} of {list(INDIRECT_ROUTE_TOKENS)}. "
            "The indirect route is the one that produced the write this rule "
            "exists to stop."
        )

    def test_binds_the_indirect_write_to_the_teammate(self, block):
        assert "that write is yours" in block, (
            "prohibition names indirect routes but no longer says the "
            "resulting write belongs to the teammate, so a reader can treat a "
            "script's write as somebody else's action"
        )


class TestW3BoundsAndUnconditionality:
    """The two bounds do different work and neither substitutes for the other.
    The rule must also stay unconditional: it was once gated behind a worktree
    condition, which switched it off in the case where it carries weight."""

    def test_keeps_the_target_bound(self, block):
        assert "project directory" in block and "home directory" in block, (
            "prohibition lost its target bound (a project directory or a home "
            "directory); without it a document a test builds in a temporary "
            "directory falls inside the rule"
        )

    def test_stays_unconditional_across_worktree_state(self, block):
        assert "with or without a worktree" in block, (
            "prohibition lost its unconditional statement. A worktree-gated "
            "rule is off in the one case where the file is present and the "
            "write lands on it."
        )

    def test_handoff_escape_hatch_is_a_write_not_an_edit(self, block):
        # The escape hatch must not re-narrow the class it just widened.
        assert "flag it in your handoff" in block, (
            "prohibition lost the handoff escape hatch, which is what makes "
            "the rule actionable when a task asks for a CLAUDE.md update"
        )
        assert "instead of editing it directly" not in block, (
            "the handoff escape hatch says 'instead of editing it directly', "
            "which re-narrows the widened class back to a direct edit"
        )
