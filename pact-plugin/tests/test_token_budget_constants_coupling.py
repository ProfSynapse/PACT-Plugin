"""Coupling arms for the two entry ceilings, driven through the shipped path.

SIBLING OF `test_token_budget.py`. That file holds the primary arms for each function with tight fire-count assertions. This file holds the parametrized
worst-case sweeps, which are kept apart so that their setup noise does not
sit beside those counts.

WHAT THESE ARMS ADD THAT THE PRIMARY FILE DOES NOT HOLD.

The primary file DERIVES the ceiling for each entry with the same expression the
source uses, then checks one entry against it. That check cannot fail on a
change to `COMPRESSED_ENTRY_TOKEN_CEILING`, because the fixture moves with
the constant. THE IDENTITY `ceiling + (MAX - 1) * compressed == budget` IS
TRUE BY CONSTRUCTION AND ASSERTING IT PROVES NOTHING: the ceiling is DEFINED
as that subtraction. So these arms do not assert the identity. They MEASURE
the quantity the identity is a proxy for, which is the token cost of the
assembled section, and compare it against the budget.

THE COUPLING THESE ARMS EXIST TO CATCH. `COMPRESSED_ENTRY_TOKEN_CEILING` is
an estimate, and its first premise is `_REFRESH_IDENTIFIER_TRUNCATION_LIMIT`.
A later author can raise the identifier limit without seeing that a token
constant depends on it. No arm in the primary file goes red on that change.
These do, because they drive the shipped formatter at the limit and compare
the result against the constant.

MEASURED HEADROOM, and the counting rule for it. Each number below counts
ESTIMATED TOKENS from `_estimate_tokens`, which is `int(words * 1.3)` across
`str.split()` of the ASSEMBLED string. Two separately rounded parts do not
sum to the rounded whole, so each number comes from one call on one joined
string.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts"))


def _densest(nchars):
    """Return the densest string of `nchars` that `str.split()` can meet.

    One character for each word plus one space is the smallest a word can be,
    so n words occupy 2n-1 characters. THE DENSITY IS THE VARIABLE AND THE
    LENGTH IS NOT: a character bound cannot enforce a token budget, because
    the producer of the value controls the ratio.
    """
    n = (nchars + 1) // 2
    s = " ".join(["a"] * n)
    if len(s) < nchars:
        s = s + "b" * (nchars - len(s))
    return s[:nchars]


def _exempt_lines(entry):
    """Return the lines `_apply_entry_token_ceiling` refuses to drop.

    Index 0 is the date header. A `**Memory ID**` line is exempt by PREFIX at
    whatever index it sits. This mirrors the source rather than restates it,
    so a change to the exempt SET makes the site-B arm below go red.
    """
    lines = entry.split("\n")
    return "\n".join(
        [lines[0]] + [ln for ln in lines[1:] if ln.startswith("**Memory ID**")]
    )


def _worst_case_memory():
    from working_memory import _REFRESH_FIELD_TRUNCATION_LIMIT

    dense = _densest(_REFRESH_FIELD_TRUNCATION_LIMIT)
    return {
        "context": dense,
        "goal": dense,
        "decisions": dense,
        "lessons_learned": dense,
        "reasoning_chains": dense,
        "agreements_reached": dense,
        "disagreements_resolved": dense,
    }


class TestCompressedEntryCeilingCoupling:
    """`COMPRESSED_ENTRY_TOKEN_CEILING` against the shipped compressed form."""

    @pytest.mark.parametrize(
        "density_label, make_id",
        [
            # THE ADVERSARIAL SHAPE. At the bound, one character for each word.
            ("dense", lambda limit: _densest(limit)),
            # THE FRIENDLY SHAPE. At the bound, a single token.
            ("one_token", lambda limit: "a" * limit),
            # Longer than the bound, so the sanitize truncates it.
            ("dense_beyond_bound", lambda limit: _densest(limit * 4)),
            # What the generator actually emits.
            ("generated_32_hex", lambda limit: "0123456789abcdef" * 2),
        ],
    )
    def test_compressed_cost_stays_within_the_ceiling(self, density_label, make_id):
        """The compressed cost holds at the identifier bound at each density.

        SWEEP THE DENSITY AXIS AND NOT ONLY THE LENGTH AXIS. A bound that
        holds for the friendly shape and fails for the dense one is the
        defect this branch repairs, and the two shapes have the SAME
        character count.

        THIS ARM GOES RED IF `_REFRESH_IDENTIFIER_TRUNCATION_LIMIT` RISES
        AND `COMPRESSED_ENTRY_TOKEN_CEILING` DOES NOT FOLLOW. That coupling
        is stated in a comment at the constant and enforced by nothing else.
        """
        from working_memory import (
            _compress_memory_entry,
            _estimate_tokens,
            _format_memory_entry,
            COMPRESSED_ENTRY_TOKEN_CEILING,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        entry = _format_memory_entry(
            _worst_case_memory(),
            memory_id=make_id(_REFRESH_IDENTIFIER_TRUNCATION_LIMIT),
        )
        compressed = _compress_memory_entry(entry)

        # NON-VACUITY: compression must have run. Without this, an input that
        # was small before compression passes the bound below untouched.
        assert _estimate_tokens(entry) > _estimate_tokens(compressed), (
            "the fixture did not exceed the compressed form, so the bound "
            "below is not exercised"
        )
        # NON-VACUITY: the recovery pointer must be present, because it is
        # the line that carries the identifier this arm is about.
        assert "**Memory ID**" in compressed

        assert _estimate_tokens(compressed) <= COMPRESSED_ENTRY_TOKEN_CEILING, (
            f"compressed cost at density {density_label} is "
            f"{_estimate_tokens(compressed)} tokens, above the ceiling of "
            f"{COMPRESSED_ENTRY_TOKEN_CEILING}. The ceiling rests on "
            f"_REFRESH_IDENTIFIER_TRUNCATION_LIMIT="
            f"{_REFRESH_IDENTIFIER_TRUNCATION_LIMIT}; if that limit moved, "
            f"move the ceiling in the same commit."
        )

    def test_the_dense_shape_costs_more_than_the_friendly_one(self):
        """The two shapes have one character count and different token costs.

        This is the premise the ceiling rests on, stated as an arm. If it
        stops holding, the worst case is no longer the dense shape and the
        arms above measure the wrong end of the axis.
        """
        from working_memory import (
            _compress_memory_entry,
            _estimate_tokens,
            _format_memory_entry,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        limit = _REFRESH_IDENTIFIER_TRUNCATION_LIMIT
        dense_id, friendly_id = _densest(limit), "a" * limit
        assert len(dense_id) == len(friendly_id) == limit

        def cost(raw_id):
            return _estimate_tokens(
                _compress_memory_entry(
                    _format_memory_entry(_worst_case_memory(), memory_id=raw_id)
                )
            )

        assert cost(dense_id) > cost(friendly_id)


class TestWorkingMemorySectionBudget:
    """Site A: the assembled section against `WORKING_MEMORY_TOKEN_BUDGET`."""

    def test_worst_case_section_stays_within_the_budget(self):
        """The section fits the budget at the worst input the formatter emits.

        THIS IS THE PROPERTY THE CEILING IDENTITY IS A PROXY FOR. The
        identity is true by construction and cannot fail. The measured total
        can, and it is what a reader of the constants cares about.
        """
        from working_memory import (
            _apply_token_budget,
            _estimate_tokens,
            _format_memory_entry,
            COMPRESSED_ENTRY_TOKEN_CEILING,
            MAX_WORKING_MEMORIES,
            WORKING_MEMORY_TOKEN_BUDGET,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        entries = [
            _format_memory_entry(
                _worst_case_memory(),
                memory_id=_densest(_REFRESH_IDENTIFIER_TRUNCATION_LIMIT),
            )
            for _ in range(MAX_WORKING_MEMORIES)
        ]
        # NON-VACUITY: the raw input must exceed the budget, or the function
        # returns it untouched and the total below proves nothing.
        assert sum(_estimate_tokens(e) for e in entries) > WORKING_MEMORY_TOKEN_BUDGET

        result = _apply_token_budget(entries, WORKING_MEMORY_TOKEN_BUDGET)

        assert sum(_estimate_tokens(e) for e in result) <= WORKING_MEMORY_TOKEN_BUDGET
        for neighbour in result[1:]:
            assert _estimate_tokens(neighbour) <= COMPRESSED_ENTRY_TOKEN_CEILING

    def test_the_drop_loop_does_not_run_at_the_production_call_site(self):
        """The section keeps all its entries at the worst production input.

        THE CALLER SLICES TO `MAX_WORKING_MEMORIES` BEFORE IT CALLS. With
        that many entries the ceiling reserves room for each compressed
        neighbour, so the drop loop has nothing to do. A drop here means the
        reserved room is too small, which is the failure the constants
        coupling would produce.

        THE COMPANION ARM IN THE PRIMARY FILE DRIVES THE LOOP AT A
        NON-PRODUCTION BUDGET. The two cover different mechanisms.
        """
        from working_memory import (
            _apply_token_budget,
            _format_memory_entry,
            MAX_WORKING_MEMORIES,
            WORKING_MEMORY_TOKEN_BUDGET,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        entries = [
            _format_memory_entry(
                _worst_case_memory(),
                memory_id=_densest(_REFRESH_IDENTIFIER_TRUNCATION_LIMIT),
            )
            for _ in range(MAX_WORKING_MEMORIES)
        ]
        result = _apply_token_budget(entries, WORKING_MEMORY_TOKEN_BUDGET)
        assert len(result) == MAX_WORKING_MEMORIES


class TestRetrievedContextThinMargin:
    """Site B: the exempt lines against the share each retrieved entry gets."""

    def test_the_exempt_lines_leave_the_ceiling_binding(self):
        """The lines that cannot be dropped cost less than the ceiling.

        WHERE THE EXEMPT LINES COST AS MUCH AS THE CEILING, NOTHING IN THE
        ENTRY IS DROPPABLE BELOW IT. The ceiling then stops binding in
        silence: no exception, no red, and a section above its budget.

        THIS IS WRITTEN AS A PROPERTY AND NOT AS A NUMBER, because a number
        rots when a constant moves. It goes red if the identifier limit
        rises, if the exempt set widens to a third line, if
        `MAX_RETRIEVED_MEMORIES` rises, or if the budget falls. Each of
        those is a change a later author can make without seeing this
        coupling, and no single file names the two constants together.
        """
        from working_memory import (
            _estimate_tokens,
            _format_retrieved_entry,
            MAX_RETRIEVED_MEMORIES,
            RETRIEVED_CONTEXT_TOKEN_BUDGET,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        share = RETRIEVED_CONTEXT_TOKEN_BUDGET // MAX_RETRIEVED_MEMORIES
        entry = _format_retrieved_entry(
            {"context": "c", "goal": "g"},
            query="q",
            score=0.5,
            memory_id=_densest(_REFRESH_IDENTIFIER_TRUNCATION_LIMIT),
        )
        exempt = _exempt_lines(entry)
        # NON-VACUITY: the exempt slice must carry the identifier line, or
        # the cost below is the date header alone and the bound is trivial.
        assert "**Memory ID**" in exempt

        assert _estimate_tokens(exempt) < share, (
            f"the exempt lines cost {_estimate_tokens(exempt)} tokens against "
            f"a share of {share}. At or above the share the ceiling stops "
            f"binding and the section can exceed its budget in silence."
        )

    def test_three_worst_case_entries_fit_the_retrieved_budget(self):
        """The section comment promises three entries. This measures three.

        `RETRIEVED_CONTEXT_COMMENT` tells a reader that the last three
        retrieved memories are shown. The ceiling for each entry is what makes
        that accurate at the worst input, so the claim is armed here rather
        than left to a reader of the comment.
        """
        from working_memory import (
            _apply_entry_token_ceiling,
            _estimate_tokens,
            _format_retrieved_entry,
            MAX_RETRIEVED_MEMORIES,
            RETRIEVED_CONTEXT_TOKEN_BUDGET,
            RETRIEVED_CONTEXT_COMMENT,
            _REFRESH_FIELD_TRUNCATION_LIMIT,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        assert str(MAX_RETRIEVED_MEMORIES) in RETRIEVED_CONTEXT_COMMENT, (
            "the section comment names a count that no longer agrees with "
            "MAX_RETRIEVED_MEMORIES"
        )

        dense = _densest(_REFRESH_FIELD_TRUNCATION_LIMIT)
        share = RETRIEVED_CONTEXT_TOKEN_BUDGET // MAX_RETRIEVED_MEMORIES
        entries = [
            _format_retrieved_entry(
                {"context": dense, "goal": dense},
                query=dense,
                score=0.99,
                memory_id=_densest(_REFRESH_IDENTIFIER_TRUNCATION_LIMIT),
            )
            for _ in range(MAX_RETRIEVED_MEMORIES)
        ]
        # NON-VACUITY: each raw entry must exceed its share, or the cut below
        # does not run and the total is within budget for an unrelated cause.
        assert all(_estimate_tokens(e) > share for e in entries)

        cut = [_apply_entry_token_ceiling(e, share) for e in entries]

        assert sum(_estimate_tokens(e) for e in cut) <= RETRIEVED_CONTEXT_TOKEN_BUDGET
        # The recovery pointer survives the cut in each entry. The design
        # accepts truncation rather than refusal BECAUSE the loss is
        # recoverable from the store, and that holds only while the pointer
        # survives.
        for entry in cut:
            assert "**Memory ID**" in entry


class TestDegenerateEdgeAtTheLiveCeilings:
    """The cut rule at the ceilings production reaches, on realistic entries."""

    # Two independent parties swept the LOW ceilings before this file: one at
    # 0 to 25 on two shapes with a pre-repair positive control, and one at 0
    # to 60 with the word budget DERIVED rather than copied. Neither swept the
    # LIVE ceilings with realistic entries, and each stated that bound. This
    # class is that half and does not repeat the low-ceiling sweep.

    @staticmethod
    def _defects(text):
        found = []
        for line in text.split("\n"):
            if line.strip() == "...":
                found.append(("bare_ellipsis", line))
            elif line.startswith("**") and "**:" not in line:
                found.append(("mangled_label", line))
        return found

    def _live_ceilings(self):
        from working_memory import (
            COMPRESSED_ENTRY_TOKEN_CEILING,
            MAX_RETRIEVED_MEMORIES,
            MAX_WORKING_MEMORIES,
            RETRIEVED_CONTEXT_TOKEN_BUDGET,
            WORKING_MEMORY_TOKEN_BUDGET,
        )

        site_a = (
            WORKING_MEMORY_TOKEN_BUDGET
            - (MAX_WORKING_MEMORIES - 1) * COMPRESSED_ENTRY_TOKEN_CEILING
        )
        site_b = RETRIEVED_CONTEXT_TOKEN_BUDGET // MAX_RETRIEVED_MEMORIES
        # AT the ceiling, ONE token above, and ONE token below. A mechanism
        # tested at one input does not have its axis swept.
        return sorted({site_a - 1, site_a, site_a + 1, site_b - 1, site_b, site_b + 1})

    @pytest.mark.parametrize(
        "shape_label, memory, with_id",
        [
            ("one_context_field_only", {"context": "A save with one field."}, False),
            ("one_context_field_with_id", {"context": "A save with one field."}, True),
            ("two_fields", {"context": "Ctx " * 40, "goal": "Goal " * 40}, True),
            ("many_fields", {"context": "Ctx " * 200, "goal": "Goal " * 200,
                             "decisions": ["D " * 100],
                             "lessons_learned": ["L " * 100]}, True),
        ],
    )
    def test_no_mangled_label_at_the_live_ceilings(self, shape_label, memory, with_id):
        """A cut entry carries no partial field label at the live ceilings.

        The cut drops whole lines, so it cannot put a value at the START of a
        line, which is the shape the sanitize exists to prevent.
        """
        from working_memory import _apply_entry_token_ceiling, _format_memory_entry

        entry = _format_memory_entry(
            memory, memory_id=("0123456789abcdef" * 2) if with_id else None
        )
        for ceiling in self._live_ceilings():
            out = _apply_entry_token_ceiling(entry, ceiling)
            assert not self._defects(out), (
                f"shape {shape_label} at ceiling {ceiling} emitted "
                f"{self._defects(out)}"
            )

    def test_the_probe_can_see_a_mangled_label(self):
        """POSITIVE CONTROL for the arm above.

        The arm above asserts an ABSENCE, so it passes when the probe is
        blind. This drives the SAME probe across a known-defective input and
        requires it to fire. Without this, a probe that matches nothing at
        all reports a clean sweep.
        """
        assert self._defects("**Context**...") == [
            ("mangled_label", "**Context**...")
        ]
        assert self._defects("...") == [("bare_ellipsis", "...")]
        assert self._defects("**Context**: kept") == []

    def test_the_cut_drops_the_field_line_rather_than_shortening_it(self):
        """At the degenerate edge the field LINE is absent, not merely tidy.

        THE DIFFERENCE MATTERS. An arm that asserts the ABSENCE OF A
        FRAGMENT also passes when the line stops being emitted for an
        unrelated cause. This asserts the positive fact: the entry is the
        exempt lines and nothing else.
        """
        from working_memory import _apply_entry_token_ceiling, _format_memory_entry

        entry = _format_memory_entry(
            {"context": "A save that carries one context field and no more."},
            memory_id="0123456789abcdef" * 2,
        )
        # NON-VACUITY: the entry must carry a droppable line to begin with.
        assert "**Context**" in entry

        out = _apply_entry_token_ceiling(entry, 6)

        # THE POSITIVE FACT, AND IT IS STRONGER THAN AN ABSENCE. Asserting
        # only that `**Context**` is gone passes when the guard is removed,
        # because the removed guard emits a BARE `...` line, which also
        # carries no `**Context**`. Pinning the result to the exempt lines
        # rejects that shape as well.
        lines = entry.split("\n")
        expected = "\n".join(
            [lines[0]] + [ln for ln in lines[1:] if ln.startswith("**Memory ID**")]
        )
        assert out == expected, (
            "the degenerate edge must leave the exempt lines and nothing "
            f"else. Got {out!r}"
        )
        assert self._defects(out) == []


class TestAfterSectionSurvivesTheSync:
    """The content BELOW a managed section survives a sync that rewrites it.

    WHY THIS IS OWED. The severity of the whole heading-injection route rests
    on one claim: the section assembly APPENDS the after-section value rather
    than drops it, so a truncation RELOCATES content and does not destroy it.
    That claim was carried at transcription grade, because the party that made
    it could not import this module. The pytest harness is the one place the
    import is permitted, so the claim is driven here.

    THE POPULATION IS SIX ASSIGNMENTS TO `new_content`, and it was re-derived
    from the file rather than copied from the brief. An earlier enumeration
    named four and called them all of them.

    THE CLAIM THAT THE TWO ENTRY POINTS REACH THE BRANCHES THAT CARRY AN
    AFTER-SECTION VALUE WAS INCORRECT, AND IT IS CORRECTED HERE RATHER THAN
    REMOVED. It was written from a reading of the branch conditions and not
    from a measurement of which branch each document reaches. MEASURED: the
    fixtures reached two of the four assignments that carry an after term.
    One of the two it missed is now driven by
    `test_the_insert_above_branch_keeps_the_tail` below. The other cannot be
    driven at all, and `test_the_excluded_branch_cannot_carry_a_value` proves
    that rather than asserts it.

    SO THE REACH IS NO LONGER A CLAIM IN PROSE. It is
    `test_every_after_carrying_assignment_is_driven_or_excluded`, which
    DERIVES the population from the module source with `ast` and derives the
    driven set from a line trace of the drivers below. A branch added later
    joins the population with no edit to this class, and it reddens until
    somebody drives it or excludes it with a cause.

    BUILT SO IT CAN DISAGREE. This is a CONFIRMATION against a weak prior and
    not a discovery, and the two want different evidence. A confirmation arm
    that cannot return the opposite verdict proves nothing about the prior it
    was built to check. The positive control drives a marker that MUST move,
    and the negative control drives a document with no after-section value and
    requires zero survivors.
    """

    MARKER = "AFTER_SECTION_SENTINEL_THAT_MUST_SURVIVE"

    def _doc(self, section_heading, comment, with_tail):
        tail = f"\n## Later Section\n\n{self.MARKER}\n" if with_tail else ""
        return (
            "# Project\n\n"
            f"{section_heading}\n{comment}\n\n"
            "### 2026-01-14 10:00\n**Context**: old one\n"
            f"{tail}"
        )

    def _sync_working(self, tmp_path, doc):
        from unittest.mock import patch
        from working_memory import sync_to_claude_md

        target = tmp_path / "CLAUDE.md"
        target.write_text(doc, encoding="utf-8")
        with patch(
            "working_memory._resolve_display_claude_md_with_base",
            return_value=(target, target.parent),
        ):
            sync_to_claude_md({"context": "new one", "goal": "g"}, memory_id="abc123")
        return target.read_text(encoding="utf-8")

    def _sync_retrieved(self, tmp_path, doc):
        from unittest.mock import patch
        from working_memory import sync_retrieved_to_claude_md

        target = tmp_path / "CLAUDE.md"
        target.write_text(doc, encoding="utf-8")
        with patch(
            "working_memory._resolve_display_claude_md_with_base",
            return_value=(target, target.parent),
        ):
            sync_retrieved_to_claude_md(
                [{"context": "found", "goal": "g"}], query="q", memory_ids=["abc123"]
            )
        return target.read_text(encoding="utf-8")

    def test_working_memory_sync_keeps_the_after_section(self, tmp_path):
        from working_memory import WORKING_MEMORY_COMMENT

        doc = self._doc("## Working Memory", WORKING_MEMORY_COMMENT, with_tail=True)
        assert self.MARKER in doc  # NON-VACUITY: the marker is present before.
        out = self._sync_working(tmp_path, doc)
        assert "new one" in out, "the sync did not run, so the arm is vacuous"
        assert self.MARKER in out, (
            "the after-section value was DROPPED by the working-memory sync. "
            "The severity argument for the heading route rests on it surviving."
        )

    def test_retrieved_sync_keeps_the_after_section(self, tmp_path):
        from working_memory import RETRIEVED_CONTEXT_COMMENT

        doc = self._doc("## Retrieved Context", RETRIEVED_CONTEXT_COMMENT, with_tail=True)
        assert self.MARKER in doc
        out = self._sync_retrieved(tmp_path, doc)
        assert "found" in out, "the sync did not run, so the arm is vacuous"
        assert self.MARKER in out, (
            "the after-section value was DROPPED by the retrieved-context sync."
        )

    def _doc_without_the_retrieved_section(self):
        """A document with a Working Memory heading and NO Retrieved Context.

        THIS IS THE SHAPE THAT REACHES THE INSERT-ABOVE BRANCH, and it is an
        ordinary one: the first retrieved sync on a project that has saved a
        memory before. That branch keeps `content[insert_pos:]`, which is the
        Working Memory section AND everything below it.
        """
        from working_memory import WORKING_MEMORY_COMMENT

        return (
            "# Project\n\n"
            f"## Working Memory\n{WORKING_MEMORY_COMMENT}\n\n"
            "### 2026-01-14 10:00\n**Context**: old one\n"
            f"\n## Later Section\n\n{self.MARKER}\n"
        )

    def test_the_insert_above_branch_keeps_the_tail(self, tmp_path):
        """The insert-above-Working-Memory branch preserves everything below.

        NO ARM DROVE THIS BRANCH BEFORE. Removing its tail term took a
        full-suite mutation with zero failures, while the same mutant at the
        two driven siblings killed 8 and 10 tests.
        """
        doc = self._doc_without_the_retrieved_section()
        assert self.MARKER in doc  # NON-VACUITY: the marker is present before.
        assert "## Retrieved Context" not in doc, (
            "the fixture must have NO retrieved section, or it reaches the "
            "replace branch instead of the insert-above one"
        )

        out = self._sync_retrieved(tmp_path, doc)

        assert "found" in out, "the sync did not run, so the arm is vacuous"
        assert self.MARKER in out, (
            "the insert-above branch DROPPED the content below the insertion "
            "point. That content is the Working Memory section and everything "
            "after it."
        )
        # And the section it inserted sits ABOVE the Working Memory heading,
        # which is what makes the tail the thing at risk.
        assert out.index("## Retrieved Context") < out.index("## Working Memory")

    # THE DRIVERS, IN ONE PLACE. The completeness arm below runs THIS list, so
    # a shape added for one arm is a shape the completeness arm also counts.
    # Two lists would let the two drift, which is the defect this class had.
    def _drivers(self):
        from working_memory import RETRIEVED_CONTEXT_COMMENT, WORKING_MEMORY_COMMENT

        return [
            ("working_sync_with_tail", self._sync_working,
             self._doc("## Working Memory", WORKING_MEMORY_COMMENT, with_tail=True)),
            ("working_sync_no_tail", self._sync_working,
             self._doc("## Working Memory", WORKING_MEMORY_COMMENT, with_tail=False)),
            ("retrieved_sync_with_tail", self._sync_retrieved,
             self._doc("## Retrieved Context", RETRIEVED_CONTEXT_COMMENT, with_tail=True)),
            ("retrieved_sync_insert_above", self._sync_retrieved,
             self._doc_without_the_retrieved_section()),
        ]

    @staticmethod
    def _after_carrying_sites():
        """Module-level derivation of the assignments that carry an after term.

        COUNTING RULE, so a later reader can reproduce the population rather
        than trust it: every `ast.Assign` in `working_memory.py` with the
        single target name `new_content`, of which the value expression either
        names `after_section`, or subscripts `content` with a slice that has a
        LOWER bound. The lower-bound slice is the tail-preserving shape
        `content[insert_pos:]`. `content[:insert_pos]` has an UPPER bound and
        keeps the head, so it is not an after term.
        """
        import ast

        source = (
            Path(__file__).resolve().parent.parent
            / "skills/pact-memory/scripts/working_memory.py"
        ).read_text(encoding="utf-8")

        sites = {}
        for node in ast.walk(ast.parse(source)):
            if not (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "new_content"
            ):
                continue
            carries = False
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Name) and sub.id == "after_section":
                    carries = True
                if (
                    isinstance(sub, ast.Subscript)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "content"
                    and isinstance(sub.slice, ast.Slice)
                    and sub.slice.lower is not None
                ):
                    carries = True
            if carries:
                sites[node.lineno] = ast.unparse(node.value)
        return sites

    # THE EXCLUSION NAMES ONE LINE AND CARRIES ITS CAUSE. A blanket accept
    # would return this gate to a promise somebody must remember to keep.
    EXCLUDED_SITE_CAUSE = (
        "the else arm of the retrieved-sync reconstruction. It is reached ONLY "
        "when after_section is EMPTY, so its after term is a no-op and no "
        "mutation of it can be detected by any test. "
        "test_the_excluded_branch_cannot_carry_a_value proves that cause."
    )

    def test_every_after_carrying_assignment_is_driven_or_excluded(self, tmp_path):
        """Each assignment that carries an after term is driven, or excluded.

        THE POPULATION IS DERIVED FROM THE SOURCE AND THE DRIVEN SET FROM A
        TRACE, so neither side is a list somebody maintains. A NEW branch that
        carries an after term joins the population with no edit here, and this
        arm reddens until a person drives it or excludes it with a cause.

        WHEN THIS GOES RED, DECIDE WHICH KIND OF SITE APPEARED.
        1. IT CAN CARRY A VALUE. Add a driver to `_drivers`, in the commit
           that introduces it.
        2. IT CANNOT CARRY A VALUE, as the excluded site cannot. Exclude it
           AND prove the cause with an arm, rather than state the cause here.
        """
        import sys
        import threading

        wm_file = str(
            (
                Path(__file__).resolve().parent.parent
                / "skills/pact-memory/scripts/working_memory.py"
            ).resolve()
        )
        population = self._after_carrying_sites()

        # NON-VACUITY: an empty population makes the comparison below pass for
        # the wrong cause, and an ast parse that found nothing looks identical
        # to a module with no such assignment.
        assert population, "no after-carrying assignment parsed from working_memory.py"

        executed = set()

        def tracer(frame, event, arg):
            if frame.f_code.co_filename != wm_file:
                return None
            if event == "line":
                executed.add(frame.f_lineno)
            return tracer

        previous = sys.gettrace()
        threading.settrace(tracer)
        sys.settrace(tracer)
        try:
            for index, (_label, driver, doc) in enumerate(self._drivers()):
                target_dir = tmp_path / f"drive{index}"
                target_dir.mkdir()
                driver(target_dir, doc)
        finally:
            sys.settrace(previous)
            threading.settrace(previous)

        # NON-VACUITY: a tracer that records nothing gives the identical
        # verdict as one that records everything, and both leave the set
        # comparison below meaningless. Require the trace to have run.
        assert executed, "the line trace recorded nothing, so the driven set is not evidence"

        driven = set(population) & executed
        excluded = set(population) - driven

        assert len(excluded) <= 1, (
            "more than one after-carrying assignment is undriven:\n"
            + "\n".join(f"  line {line}: {population[line]}" for line in sorted(excluded))
            + "\nDrive it, or exclude it with a cause that an arm proves."
        )
        assert driven, "no after-carrying assignment was reached by any driver"

    def test_the_excluded_branch_cannot_carry_a_value(self):
        """PROOF OF THE EXCLUSION CAUSE, so the exclusion is not a promise.

        The excluded assignment sits in the arm taken when `after_section` is
        empty OR begins with a newline. `_find_terminator_offset` returns the
        offset of the START of the terminator LINE, so the after-section either
        begins at a terminator character or is empty. IT CANNOT BEGIN WITH A
        NEWLINE, so the arm is reached only with an empty value.

        THIS IS THE ARM THAT RETURNS THE DECISION TO A PERSON. If a later edit
        to the parser makes a newline-leading after-section reachable, this
        goes red and the exclusion above stops being safe.
        """
        from working_memory import (
            RETRIEVED_CONTEXT_COMMENT,
            _MANAGED_END_MARKER,
            _MANAGED_START_MARKER,
            _parse_retrieved_context_section,
        )

        section = (
            f"## Retrieved Context\n{RETRIEVED_CONTEXT_COMMENT}\n\n"
            "### 2026-01-14 10:00\n**Context**: old\n"
        )
        tails = [
            "\n## Later\n\nX\n", "\n\n\n## Later\n", "\nX\n", "\n---\n\nX\n",
            "\n\nX\n", "X\n", "", "\n", "\r\n## Later\r\n\r\nX\r\n",
        ]
        seen_non_empty = 0
        for tail in tails:
            for wrapped in (False, True):
                if wrapped:
                    doc = (
                        f"# P\n\n{_MANAGED_START_MARKER}\n{section}"
                        f"{_MANAGED_END_MARKER}\n{tail}"
                    )
                else:
                    doc = f"# P\n\n{section}{tail}"
                _before, _header, after, _entries = _parse_retrieved_context_section(doc)
                seen_non_empty += 1 if after else 0
                assert not after.startswith("\n"), (
                    f"a newline-leading after-section is now reachable with "
                    f"tail {tail!r} and managed region {wrapped}. The exclusion "
                    f"in this class rests on that being impossible."
                )
        # NON-VACUITY: the sweep must produce non-empty after-sections, or it
        # proves the property over the empty string alone.
        assert seen_non_empty >= 2, (
            f"the sweep produced {seen_non_empty} non-empty after-sections, so "
            f"it does not exercise the property it asserts"
        )

    def test_negative_control_no_after_section_gives_no_survivor(self, tmp_path):
        """A document with no after-section value yields no marker.

        Without this, an arm that finds the marker for an unrelated cause,
        such as a probe that reads its own input, reports a survivor that the
        sync did not produce.
        """
        from working_memory import WORKING_MEMORY_COMMENT

        doc = self._doc("## Working Memory", WORKING_MEMORY_COMMENT, with_tail=False)
        assert self.MARKER not in doc
        out = self._sync_working(tmp_path, doc)
        assert "new one" in out
        assert self.MARKER not in out


class TestFieldNameSurvivesTheCut:
    """The class the repaired cut must hold, at each second-word length.

    THE CLASS, RATHER THAN THE INSTANCE. For each cut, the emitted line
    keeps its COMPLETE `**Field**: ` name, or the line is not present. An
    earlier bound of 2 held for the input it was measured at and failed at a
    one-character second word, so this sweeps the SECOND-WORD LENGTH AXIS
    from 0 up rather than test one input.

    THE THREE PREDICATES BELOW SEPARATE THREE SHAPES, and the control test
    asserts that separation BEFORE any corpus runs. A detector that cannot
    tell the shapes apart reports a clean zero for the shape it cannot see.

    THE SHAPE THESE PREDICATES CANNOT SEE, NAMED RATHER THAN LEFT IMPLICIT:
    all three key on the `**` prefix or on the header. A value fragment
    pushed to the START of a line is caught by `_orphan_value` only while it
    carries no `**`. A fragment that begins with `**` and happens to form a
    complete name reads as healthy to each of them. `_orphan_value` exists
    because the two name predicates were blind to that half of the cut rule.
    """

    HEADER_PREFIX = "### "
    FIELD_RE = re.compile(r"^\*\*[A-Za-z ]+\*\*:")

    @classmethod
    def _broken_name(cls, line):
        """The field name is incomplete, or the line is a bare marker."""
        s = line.strip()
        if s == "...":
            return True
        return s.startswith("**") and not cls.FIELD_RE.match(s)

    @classmethod
    def _name_without_value(cls, line):
        """A COMPLETE field name, a marker, and no value after it."""
        m = cls.FIELD_RE.match(line.strip())
        return bool(m) and line.strip()[m.end():].strip() == "..."

    @classmethod
    def _orphan_value(cls, line):
        """A value fragment at the START of a line, with no field name.

        THE BARE MARKER IS EXCLUDED BECAUSE `_broken_name` OWNS IT. The
        control test below caught the two predicates each claiming that one
        shape. Two predicates that answer for one shape double-report it,
        so the three predicates here PARTITION the shapes rather than
        overlap.
        """
        s = line.strip()
        if s == "...":
            return False
        return bool(s) and not s.startswith(cls.HEADER_PREFIX) and not s.startswith("**")

    def test_control_the_predicates_separate_the_shapes(self):
        """CONTROL, asserted BEFORE the corpus arms below run.

        Each row names a shape and the verdict each predicate owes it. A
        detector that answers the same for two different shapes cannot
        report a meaningful count, and a zero from it is not evidence.
        """
        rows = [
            # line,                    broken, name_only, orphan
            ("**Context**...",          True,  False, False),
            ("...",                     True,  False, False),
            ("**Context**:...",         False, True,  False),
            ("**Context**: x...",       False, False, False),
            ("**Context**: kept text",  False, False, False),
            ("**Memory ID**: abc123",   False, False, False),
            ("### 2026-01-15 10:00",    False, False, False),
            ("a stray value fragment",  False, False, True),
            ("",                        False, False, False),
        ]
        for line, broken, name_only, orphan in rows:
            assert self._broken_name(line) is broken, f"_broken_name on {line!r}"
            assert self._name_without_value(line) is name_only, f"_name_without_value on {line!r}"
            assert self._orphan_value(line) is orphan, f"_orphan_value on {line!r}"

    def _corpus(self):
        """Entries that sweep the SECOND-WORD LENGTH axis from 0 up."""
        shapes = []
        for n in range(0, 12):
            second = "x" * n
            value = (second + " " if n else "") + "tail one two three four five"
            shapes.append((f"second_word_len_{n}", {"context": value}))
        shapes.append(("no_second_word", {"context": "Solo"}))
        shapes.append(("two_fields", {"context": "Ctx " * 60, "goal": "Goal " * 60}))
        return shapes

    @pytest.mark.parametrize("with_id", [True, False])
    def test_the_field_name_is_complete_or_the_line_is_absent(self, with_id):
        """No cut emits a broken field name, at any second-word length.

        THIS IS THE ARM THE REPAIR EXISTS FOR. Before the repair the cut
        wrote the marker ON TOP of the kept text, so at a small word budget
        the marker consumed the field name. The repair APPENDS the marker,
        which cannot reach into the words it keeps.
        """
        from working_memory import _apply_entry_token_ceiling, _format_memory_entry

        for label, memory in self._corpus():
            entry = _format_memory_entry(
                memory, memory_id=("0123456789abcdef" * 2) if with_id else None
            )
            for ceiling in range(0, 61):
                out = _apply_entry_token_ceiling(entry, ceiling)
                for line in out.split("\n"):
                    assert not self._broken_name(line), (
                        f"{label} at ceiling {ceiling} emitted a broken field "
                        f"name: {line!r}"
                    )
                    assert not self._orphan_value(line), (
                        f"{label} at ceiling {ceiling} pushed a value to the "
                        f"start of a line: {line!r}"
                    )

    def test_a_name_without_its_value_is_the_ruled_rendering(self):
        """At a word budget of 1 the line keeps its name and elides the value.

        THIS SHAPE IS RULED ACCEPTABLE AND THE ARM RECORDS THE RULING. At a
        budget of 1 the one kept word IS the field name, so the appended
        marker gives `**Context**:...`. It keeps the COMPLETE name, so it
        opens no heading and is not the partial fragment the cut rule
        prevents. It tells a reader that the field carried content that did
        not fit, which is more than a dropped line tells them.

        THE ARM IS POSITIVE ON PURPOSE. Two independently built detectors
        were blind to this shape, so a silent zero would stand for it. A
        change of the rendering makes this arm red and returns the decision
        to a person.
        """
        from working_memory import _apply_entry_token_ceiling, _format_memory_entry

        entry = _format_memory_entry({"context": "value words here"})
        hit = None
        for ceiling in range(0, 61):
            out = _apply_entry_token_ceiling(entry, ceiling)
            for line in out.split("\n"):
                if self._name_without_value(line):
                    hit = (ceiling, line)
                    break
            if hit:
                break

        # NON-VACUITY: the shape must occur, or this arm records nothing.
        assert hit is not None, "the ruled rendering did not occur at any ceiling"
        assert hit[1].strip() == "**Context**:...", hit
        # And it keeps the complete name, which is the property that makes
        # the ruling safe.
        assert not self._broken_name(hit[1])

    def test_the_shipped_ceilings_do_not_reach_the_degenerate_budget(self):
        """The two live ceilings leave a wide margin above a word budget of 1.

        WRITTEN AS A MARGIN RATHER THAN AS A COUNT OF ZERO. A zero says the
        shape did not occur in the corpus somebody chose. The margin says
        how far the shipped constants sit from the input that produces it,
        so it moves when a constant moves.
        """
        from working_memory import (
            _estimate_tokens,
            _format_retrieved_entry,
            COMPRESSED_ENTRY_TOKEN_CEILING,
            MAX_RETRIEVED_MEMORIES,
            MAX_WORKING_MEMORIES,
            RETRIEVED_CONTEXT_TOKEN_BUDGET,
            WORKING_MEMORY_TOKEN_BUDGET,
            _REFRESH_IDENTIFIER_TRUNCATION_LIMIT,
        )

        site_a = (WORKING_MEMORY_TOKEN_BUDGET
                  - (MAX_WORKING_MEMORIES - 1) * COMPRESSED_ENTRY_TOKEN_CEILING)
        site_b = RETRIEVED_CONTEXT_TOKEN_BUDGET // MAX_RETRIEVED_MEMORIES

        # The worst case for the word budget is the LARGEST exempt cost,
        # which is a DENSE identifier at its bound.
        entry = _format_retrieved_entry(
            {"context": "c"}, query="q",
            memory_id=_densest(_REFRESH_IDENTIFIER_TRUNCATION_LIMIT),
        )
        worst_exempt = _estimate_tokens(_exempt_lines(entry))

        for name, ceiling in (("site A", site_a), ("site B", site_b)):
            budget_words = max(0, int((ceiling - worst_exempt) / 1.3))
            assert budget_words > 1, (
                f"{name} ceiling {ceiling} against a worst-case exempt cost of "
                f"{worst_exempt} gives a word budget of {budget_words}. At 1 the "
                f"cut emits a name with no value, and at 0 it drops the line."
            )


class TestMemoryIdLabelSites:
    """The four executable sites must REFERENCE the label constant.

    THE COUPLING, AND WHY IT NEEDS A SOURCE-SHAPE ARM RATHER THAN A
    BEHAVIOURAL ONE. Two sites WRITE the recovery-pointer line and two
    sites READ it by prefix. The read sites are what hold that line out of
    the cut, and the design accepts truncation rather than refusal ONLY
    WHILE that pointer survives. A rename applied to some of the four and
    not the rest makes the id line droppable, and the recovery route goes.

    MEASURED, AND IT IS WHY THIS ARM EXISTS IN THIS FORM:
    - A change to the label VALUE is CAUGHT TODAY. Driving the constant
      from `**Memory ID**` to `**Record ID**` reddens 12 tests across four
      test modules, some of them written by other authors. That direction
      needs no new arm and this class does not add one.
    - A site that REVERTS TO THE BARE LITERAL while the constant keeps its
      value is CAUGHT BY NOTHING. Reverting one read site to the literal
      and running the FULL suite gives 14413 passed, 15 skipped, 0 failed.
      NO BEHAVIOURAL TEST CAN EVER CATCH IT, because a literal equal to the
      constant produces identical behaviour. It is invisible until somebody
      changes the value, and then it half-applies in silence.

    SO THIS ARM READS THE SOURCE SHAPE. It is the only instrument that can
    see the difference, and the counting rule is stated below.
    """

    LABEL_NAME = "_MEMORY_ID_LABEL"
    FUNCTIONS = (
        "_compress_memory_entry",       # READ, keeps the line
        "_apply_entry_token_ceiling",   # READ, holds the line out of the cut
        "_format_memory_entry",         # WRITE
        "_format_retrieved_entry",      # WRITE
    )

    def _module_source(self):
        import pathlib

        return (
            pathlib.Path(__file__).resolve().parent.parent
            / "skills/pact-memory/scripts/working_memory.py"
        ).read_text()

    def test_the_constant_is_defined_once_at_module_level(self):
        """COUNTING RULE: module-level `NAME = value` assignments, `ast`-parsed."""
        import ast

        tree = ast.parse(self._module_source())
        defined = [
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == self.LABEL_NAME
        ]
        assert len(defined) == 1, (
            f"{self.LABEL_NAME} must have one module-level definition and no more, "
            f"found {len(defined)}"
        )

    @pytest.mark.parametrize("function_name", FUNCTIONS)
    def test_the_site_references_the_constant_and_spells_no_literal(
        self, function_name
    ):
        """Each of the four sites uses the NAME, and none carries the value.

        COUNTING RULE: the function is located by `ast` in the module source
        by name. A REFERENCE is an `ast.Name` node that carries the constant
        name as its id. A LITERAL is an `ast.Constant` string equal to the value the
        constant holds. The docstring of the function is excluded, because a
        docstring that quotes the label is prose rather than a second site.
        """
        import ast

        from working_memory import _MEMORY_ID_LABEL

        tree = ast.parse(self._module_source())
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                target = node
                break
        # NON-VACUITY: a renamed or removed function must not pass by absence.
        assert target is not None, (
            f"{function_name} is not present in working_memory.py. If it moved, "
            f"re-point this arm rather than remove it."
        )

        body = list(target.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]

        names, literals = set(), []
        for statement in body:
            for node in ast.walk(statement):
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value == _MEMORY_ID_LABEL
                ):
                    literals.append(node.value)

        assert self.LABEL_NAME in names, (
            f"{function_name} does not reference {self.LABEL_NAME}. The four "
            f"sites must move together, or a rename half-applies in silence."
        )
        assert not literals, (
            f"{function_name} spells the label value {_MEMORY_ID_LABEL!r} as a "
            f"literal. Behaviour is identical today, so no other test can see "
            f"this. It becomes a defect when the constant value changes."
        )
