"""The two-rule gate repair: the same-slice decision and the conjunction.

WHAT THE TWO RULES ARE.
  RULE 1, the same-slice decision. The two sides of one comparison are counted
  across ONE slice. A difference taken across two different slices is not a
  comparison, and that defect is the STRADDLE.
  RULE 2, the conjunction predicate. A heading that is date-led AND carries no
  `<!-- pinned: -->` marker is a memory entry rather than a pin.

🔴 THE TWO ARE COUPLED AND THE ARMS BELOW MEASURE THE COUPLING. The whole-text
fallback of Rule 1 KEEPS the memory entries, and Rule 2 is what drops them. The
ablation class at the end is what shows each rule earns its place IN THE
PRESENCE OF the other, which a mutation of one rule alone cannot show.
"""
import re
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).parent.parent / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from shared.claude_md_manager import (  # noqa: E402
    MANAGED_START_MARKER,
    MANAGED_END_MARKER,
)

PIN_A = "<!-- pinned: 2026-08-01 -->\n### Merge guard purpose\nbody a\n"
PIN_B = "<!-- pinned: 2026-08-02 -->\n### Platform constraint\nbody b\n"
PIN_C = "<!-- pinned: 2026-08-03 -->\n### Version discipline\nbody c\n"
PIN_D = "<!-- pinned: 2026-08-04 -->\n### Count parameter\nbody d\n"
PIN_E = "<!-- pinned: 2026-08-05 -->\n### Fifth pin\nbody e\n"
# A pin the curator titled with a bare date. It CARRIES its marker, so the
# conjunction keeps it. A date-only rule would drop it, which is the mutation
# the E2 arm below kills.
PIN_DATE_TITLED = "<!-- pinned: 2026-08-06 -->\n### 2026-08-06\nbody f\n"
MEM_1 = "### 2026-08-11 19:11\n**Context**: one\n"
MEM_2 = "### 2026-08-11 20:02\n**Context**: two\n"
# Content OUTSIDE the managed region. Without a `### ` heading here the two
# counter branches agree BY CONSTRUCTION and the straddle cases cannot bite.
# That vacuity cost the design one whole run, so this file asserts it.
OUT_OF_REGION = "## User notes\n\n### My own heading\nprose the user wrote\n"
# The same out-of-region content with NO `### ` heading in it. The PAIR of
# fixtures is what lets a case move the WHOLE-TEXT count while it leaves the
# MANAGED-REGION count alone. One fixture cannot do that, because the two sides
# then carry the same outside content and the two slices agree by construction.
OUT_OF_REGION_PLAIN = "## User notes\n\nprose the user wrote\n"


def managed(pins, mems=(), outside=""):
    """A document that CARRIES the managed markers."""
    return (
        "# Project Memory\n\n"
        f"{outside}"
        f"{MANAGED_START_MARKER}\n"
        "## Pinned Context\n\n"
        f"{''.join(pins)}"
        "\n## Working Memory\n\n"
        f"{''.join(mems)}"
        f"{MANAGED_END_MARKER}\n"
    )


def unmanaged(pins, mems=(), outside=""):
    """The same content with NO managed markers, which is the other branch."""
    return (
        "# Project Memory\n\n"
        f"{outside}"
        "## Pinned Context\n\n"
        f"{''.join(pins)}"
        "\n## Working Memory\n\n"
        f"{''.join(mems)}"
    )


def verdict_by_slice(gate, old, new, slice_name):
    """Count the two sides across ONE named slice and report the verdict.

    It reproduces what each branch of the selection would decide, so an arm can
    assert that the two branches DISAGREE on a fixture pair. An arm for a branch
    is vacuous while the two branches agree, and this is what measures that.
    """
    from shared.claude_md_manager import extract_managed_region

    if slice_name == "region":
        old_body = extract_managed_region(old)[0]
        new_body = extract_managed_region(new)[0]
    else:
        old_body, new_body = old, new
    return gate._count_pin_comments(new_body) > gate._count_pin_comments(old_body)


def fires(gate, old, new, tool="Edit", tmp_path=None):
    """Drive the shipped decision. True means the edit of a user is DENIED."""
    if tool == "Write":
        target = tmp_path / "CLAUDE.md"
        target.write_text(old, encoding="utf-8")
        return gate._is_add_shaped_edit({"content": new}, target, "Write")
    return gate._is_add_shaped_edit(
        {"old_string": old, "new_string": new}, Path("/nonexistent"), "Edit"
    )


@pytest.fixture
def gate():
    import pin_staleness_gate
    return pin_staleness_gate


# =========================================================================
# The fixtures must be able to bite. This is the vacuity gate the design
# lost a run to.
# =========================================================================

class TestTheStraddleFixturesCanBite:
    def test_out_of_region_content_carries_a_pin_shaped_heading(self):
        """NON-VACUITY, AND IT IS THE ONE THE DESIGN LEARNED THE HARD WAY.

        The two counter branches differ ONLY in what they exclude. A document
        with nothing outside the managed region makes the whole-text count and
        the managed-region count agree by construction, so a straddle case
        passes for a reason that has nothing to do with the repair.
        """
        assert re.search(r"^### ", OUT_OF_REGION, re.M), (
            "the out-of-region fixture carries no `### ` heading, so the two "
            "slices agree by construction and each straddle arm below is "
            "vacuous"
        )

    def test_the_two_slices_disagree_on_the_straddle_fixture(self, gate):
        """The fixture separates the two branches. Measured, not assumed."""
        doc = managed([PIN_A], outside=OUT_OF_REGION)
        from shared.claude_md_manager import extract_managed_region
        whole = gate._count_pin_comments(doc)
        region = gate._count_pin_comments(extract_managed_region(doc)[0])
        assert whole != region, (
            f"whole-text count {whole} equals managed-region count {region}, "
            f"so this fixture cannot exhibit a straddle"
        )


# =========================================================================
# RULE 1, the same-slice decision.
# =========================================================================

class TestRule1TheDecisionOwnsTheSlice:
    def test_s1_a_straddle_that_moves_no_pin_stays_quiet(self, gate, tmp_path):
        """S1. The two sides reach different branches and NO pin moved.

        Before Rule 1 this OVER-BLOCKED: one side counted the managed region,
        the other counted the whole text, and the difference measured the
        slice rather than the pins.
        """
        old = managed([PIN_A, PIN_B], outside=OUT_OF_REGION)
        new = unmanaged([PIN_A, PIN_B], outside=OUT_OF_REGION)
        assert fires(gate, old, new, "Write", tmp_path) is False

    def test_s2_a_straddle_that_adds_a_pin_fires(self, gate, tmp_path):
        """S2. A TRUE add of four pins to five, across a straddle.

        🔴 THIS IS THE UNDER-BLOCK, and it is the direction this arc had not
        seen before. Today's code returns quiet on a real add. An arm that
        checks only that memory writes stopped over-blocking cannot see it.
        """
        old = unmanaged([PIN_A, PIN_B, PIN_C, PIN_D], outside=OUT_OF_REGION)
        new = managed(
            [PIN_A, PIN_B, PIN_C, PIN_D, PIN_E], outside=OUT_OF_REGION
        )
        assert fires(gate, old, new, "Write", tmp_path) is True

    def test_s3_control_out_of_region_content_and_no_straddle(
        self, gate, tmp_path
    ):
        """S3. Out-of-region content on the two sides and NO straddle.

        It separates a straddle repair from a repair that suppresses the gate.
        A change that makes the gate quiet everywhere passes S1 and fails S2,
        and this arm holds the quiet side honest.
        """
        old = managed([PIN_A, PIN_B], outside=OUT_OF_REGION)
        new = managed([PIN_A, PIN_B], mems=[MEM_1], outside=OUT_OF_REGION)
        assert fires(gate, old, new, "Write", tmp_path) is False


class TestRule1TheManagedBranchEarnsItsPlace:
    """THE BRANCH THAT TAKES THE MANAGED REGION, BOUNDED IN THE TWO DIRECTIONS.

    THE GAP THIS CLOSES WAS MEASURED RATHER THAN REASONED. The cases above
    either reach the whole-text fallback, or they reach the managed branch with
    the SAME out-of-region content on the two sides. In that second shape the
    slices count 2 against 2 inside the region and 3 against 3 across the whole
    text, so either slice returns the same verdict. The branch can then be made
    dead and 47 of 47 arms stay green.

    THE SEPARATING SHAPE IS THE ONE WHERE THE TWO SLICES DISAGREE. The managed
    region is a SUBSET of the whole text, so a change INSIDE the region moves
    the two counts together. Only a change OUTSIDE the region moves one count
    and leaves the other, so the out-of-region content must DIFFER across the
    two sides while the two sides are both managed.

    THE REMOVAL FAILS IN THE TWO DIRECTIONS AND ONE ARM BOUNDS ONE OF THEM.
    Without the branch, a user who adds a heading to their own notes is DENIED,
    and a user who adds a true pin while a heading leaves their notes is
    ALLOWED. An arm for the first direction alone leaves the second open, so
    there are two arms here and not one.
    """

    OUTSIDE_GAINS_A_HEADING = (
        (OUT_OF_REGION_PLAIN, OUT_OF_REGION),
        ([PIN_A, PIN_B], [PIN_A, PIN_B]),
    )
    A_PIN_LANDS_WHILE_THE_OUTSIDE_LOSES_ONE = (
        (OUT_OF_REGION, OUT_OF_REGION_PLAIN),
        ([PIN_A, PIN_B], [PIN_A, PIN_B, PIN_C]),
    )

    @staticmethod
    def _pair(case):
        (out_old, out_new), (pins_old, pins_new) = case
        return (
            managed(pins_old, outside=out_old),
            managed(pins_new, outside=out_new),
        )

    def test_a_heading_added_outside_the_managed_region_stays_quiet(
        self, gate, tmp_path
    ):
        """The managed region does not move. The user edits their own notes.

        A DENY here is an over-block on content the gate has no claim over,
        which is the cardinal direction for this repository.
        """
        old, new = self._pair(self.OUTSIDE_GAINS_A_HEADING)
        assert fires(gate, old, new, "Write", tmp_path) is False, (
            "a heading the user added OUTSIDE the managed region was read as a "
            "pin add, so the decision counted across the whole text while the "
            "two sides both carry the managed markers"
        )

    def test_a_pin_added_inside_fires_while_the_outside_loses_a_heading(
        self, gate, tmp_path
    ):
        """A TRUE pin add, with the whole-text count held level by the outside.

        THIS IS THE OTHER FAILURE DIRECTION OF THE SAME BRANCH. Across the whole
        text the counts are 3 against 3, so a decision that reached the whole
        text would go quiet on a real add. The arm above cannot see that.
        """
        old, new = self._pair(self.A_PIN_LANDS_WHILE_THE_OUTSIDE_LOSES_ONE)
        assert fires(gate, old, new, "Write", tmp_path) is True, (
            "a true pin add inside the managed region went unreported, because "
            "a heading left the user's own notes in the same edit and the two "
            "movements cancel in a whole-text count"
        )

    @pytest.mark.parametrize(
        "case_name",
        ["OUTSIDE_GAINS_A_HEADING", "A_PIN_LANDS_WHILE_THE_OUTSIDE_LOSES_ONE"],
    )
    def test_the_two_slices_disagree_on_each_fixture_pair(self, gate, case_name):
        """NON-VACUITY, AND THE TWO ARMS ABOVE ARE EVIDENCE ONLY WITH THIS.

        An arm for a branch says nothing while the branch it selects returns
        what the other branch returns. This measures the two verdicts and
        asserts they DIFFER, so a fixture that stops separating the branches
        reddens HERE rather than passing in silence up there.

        It also asserts the PRECONDITION: the two sides must carry the managed
        markers, or the pair never reaches the branch under test and the arms
        above pass from the fallback.
        """
        from shared.claude_md_manager import extract_managed_region

        old, new = self._pair(getattr(self, case_name))

        assert extract_managed_region(old) is not None, (
            "the OLD side carries no managed markers, so this pair takes the "
            "whole-text fallback and says nothing about the managed branch"
        )
        assert extract_managed_region(new) is not None, (
            "the NEW side carries no managed markers, so this pair takes the "
            "whole-text fallback and says nothing about the managed branch"
        )

        region = verdict_by_slice(gate, old, new, "region")
        whole = verdict_by_slice(gate, old, new, "whole")
        assert region != whole, (
            f"the managed-region slice and the whole-text slice AGREE on this "
            f"pair (both {region}), so either slice gives the same answer and "
            f"the arm built on it cannot separate the two branches"
        )


# =========================================================================
# RULE 2, the conjunction predicate.
# =========================================================================

class TestRule2TheConjunction:
    def test_e0_adding_a_memory_entry_stays_quiet(self, gate):
        """E0. The measured defect: a memory write read as a pin add."""
        assert fires(gate, "## Working Memory\n\n",
                     f"## Working Memory\n\n{MEM_1}") is False

    def test_e2_a_marked_pin_titled_a_bare_date_fires(self, gate):
        """E2. THE ARM THAT KILLS THE DATE-ONLY RULE.

        The heading is a bare date AND the entry carries its marker, so it is
        a pin. A predicate that read the heading alone would drop it and the
        gate would go quiet on a real add.
        """
        assert fires(gate, "## Working Memory\n",
                     f"{PIN_DATE_TITLED}\n## Working Memory\n") is True

    def test_e4_archiving_a_pin_while_memory_lands_stays_quiet(self, gate):
        """E4. The archive case, which is the escape from a full pin cap.

        An over-block here is the livelock the whole gate exists to prevent.
        """
        old = f"{PIN_A}## Working Memory\n\n"
        new = f"## Working Memory\n\n{MEM_1}{MEM_2}"
        assert fires(gate, old, new) is False

    def test_e1_adding_a_real_pin_through_the_edit_path_fires(self, gate):
        """E1. THE ARM THAT M2 MUST REDDEN.

        A suite that checks only that memory writes stopped over-blocking
        PASSES when the Edit path is replaced with a plain 0, because that
        stops the gate firing at all. This arm is what separates a repaired
        gate from a retired one.
        """
        assert fires(gate, "## Working Memory\n",
                     f"{PIN_A}\n## Working Memory\n") is True


class TestRule2KnownResidual:
    def test_r2_an_edit_that_adds_a_missing_marker_fires(self, gate):
        """R2, A KNOWN AND ACCEPTED RESIDUAL, PINNED SO IT CANNOT MOVE UNSEEN.

        An edit that adds a missing marker to a date-titled pin moves NO pin,
        and this gate FIRES. That is a cardinal over-block.

        WHY IT SHIPS: its trigger is one population, a date-titled pin with no
        marker, and a user ruling declares that population empty. THE ARM DOES
        NOT ENDORSE THE BEHAVIOUR. It records the accepted state so a later
        change that closes R2, or that widens it, shows up as a diff here
        rather than passing in silence.
        """
        old = "### 2026-08-06\nbody f\n"
        new = PIN_DATE_TITLED
        assert fires(gate, old, new) is True


class TestRule2TheRenameDirection:
    """A FAITHFUL RENAME OF A PIN MUST NOT BE DENIED, MEASURED AT THE COUNT.

    WHY THIS SITS HERE AND NOT WITH THE WRITERS. The date-led rule is read on
    TWO surfaces. A PREDICATE reads one heading and answers whether it is a
    memory entry. A COMPARISON reads an OLD text and a NEW text and answers
    whether a pin arrived. A rule that grows fails differently on the two, and
    an arm on the predicate cannot reach the comparison, because the comparison
    needs two documents and a predicate arm has one heading. The predicate side
    is bounded beside the writers. THIS IS THE COMPARISON SIDE.

    THE SHAPE, AND IT IS AN ORDINARY EDIT RATHER THAN AN ADVERSARIAL ONE. A user
    renames a pin and drops the date from its title. No marker is present on
    either side, because that pin was never marked. The shipped rule refuses a
    date FOLLOWED BY A TITLE, so the old title and the new title are counted
    alike and the gate stays quiet.

    GROW THE RULE AT ITS TAIL AND THE OLD TITLE BECOMES A MEMORY ENTRY. The OLD
    count FALLS, the new count is then the greater, and the decision reports an
    add where the user removed a date. A faithful rename is DENIED. That is an
    over-block, which this repository treats as the cardinal direction, and it
    is invisible to an arm that reads one heading.

    🔴 THE QUIET ARMS ARE EVIDENCE ONLY BECAUSE OF THE CONTROL BELOW. An assert
    of False passes for many reasons, and a decision that returned False for
    everything would satisfy each quiet arm here forever. The control fires on a
    true add carrying the same date-prefixed title, so a retired decision shows
    up in this class rather than in another file.
    """

    RENAMES = [
        ("### 2026-08-05 Draft notes", "### Draft notes"),
        ("### 2026-08-05 12:30 Draft notes", "### Draft notes"),
        ("### 2026-08-05  Merge guard purpose", "### Merge guard purpose"),
    ]

    @pytest.mark.parametrize("old_title,new_title", RENAMES)
    def test_a_rename_that_drops_the_date_stays_quiet(
        self, gate, old_title, new_title
    ):
        old = f"{old_title}\nbody\n"
        new = f"{new_title}\nbody\n"
        assert fires(gate, old, new) is False, (
            f"THE GATE DENIED A FAITHFUL RENAME.\n"
            f"  old title: {old_title!r}\n"
            f"  new title: {new_title!r}\n"
            f"No pin arrived. The user removed a date from a title.\n"
            f"\n"
            f"WHAT PRODUCES THIS. The date-led rule grew at its tail, so it now "
            f"accepts a date FOLLOWED BY A TITLE. The OLD title is then read as "
            f"a memory entry and drops out of the old count, the new count "
            f"becomes the greater, and the comparison reports an add.\n"
            f"\n"
            f"THIS IS AN OVER-BLOCK AND IT IS THE CARDINAL DIRECTION. The user "
            f"cannot edit Pinned Context and cannot see why. Do not repair it "
            f"here. The rule belongs to the gate, and the tail anchor is what "
            f"holds it."
        )

    def test_a_true_add_beside_a_date_prefixed_title_fires(self, gate):
        """POSITIVE CONTROL ON THE DECISION, IN THIS CLASS RATHER THAN ELSEWHERE.

        It carries the SAME date-prefixed title as the quiet arms and adds a
        second heading beside it. A decision that stopped firing at all passes
        each quiet arm above and fails here.
        """
        old = "### 2026-08-05 Draft notes\nbody\n"
        new = "### 2026-08-05 Draft notes\nbody\n### Second pin\nbody\n"
        assert fires(gate, old, new) is True, (
            "the decision went quiet on a true add, so the quiet arms above "
            "prove nothing: they pass for a decision that reports no add ever"
        )


# =========================================================================
# RULE 4, the tool name.
# =========================================================================

class TestRule4TheToolNameDecidesTheBranch:
    def test_an_edit_payload_carrying_a_content_key_takes_the_edit_branch(
        self, gate, tmp_path
    ):
        """Rule 4. The branch asks the TOOL rather than a payload key.

        An Edit payload that happens to carry a `content` key took the
        whole-document branch before this, which reads a file the Edit never
        names. The old and new strings here would FIRE on the fragment branch,
        so a wrong branch is visible rather than silent.
        """
        result = gate._is_add_shaped_edit(
            {
                "old_string": "## Working Memory\n",
                "new_string": f"{PIN_A}\n## Working Memory\n",
                "content": "decoy",
            },
            tmp_path / "absent.md",
            "Edit",
        )
        assert result is True, (
            "the decision took the Write branch on an Edit payload, so it "
            "read a file rather than the strings the Edit supplied"
        )


# =========================================================================
# ABLATION. Does each rule earn its place IN THE PRESENCE OF the other?
# =========================================================================

class TestAblationEachRuleEarnsItsPlace:
    """AN ABLATION IS NOT A MUTATION AND THE DIFFERENCE DECIDED A DESIGN ITEM.

    A MUTATION tests a part ALONE: break it and see an arm redden.
    AN ABLATION removes a part while THE OTHERS STAY and asks whether any case
    changes. A part whose repair is present twice survives every mutation and
    changes nothing when ablated. That is how the write-path bounding was found
    redundant and dropped.

    THE TWO ARMS BELOW REMOVE ONE RULE WITH THE OTHER LEFT IN PLACE. Each one
    carries a POSITIVE CONTROL that the removal took effect, because a green
    ablation is ambiguous: it can mean the part earns nothing, or it can mean
    the patch missed its target.
    """

    def test_removing_rule_2_changes_a_named_case_while_rule_1_stays(
        self, gate, monkeypatch
    ):
        """Ablate the conjunction. Rule 1 stays. E0 must change verdict.

        This is the coupling, measured: the whole-text fallback of Rule 1 keeps
        the memory entries, so with Rule 2 removed a plain memory write
        over-blocks again.
        """
        old, new = "## Working Memory\n\n", f"## Working Memory\n\n{MEM_1}"
        assert fires(gate, old, new) is False

        monkeypatch.setattr(gate, "_is_memory_entry", lambda pin: False)

        # POSITIVE CONTROL: the ablation took effect. Without this a green
        # result can mean the patch never landed.
        assert gate._count_pin_comments(MEM_1) == 1, (
            "the ablation did not reach the counter, so the result below "
            "says nothing about what Rule 2 contributes"
        )
        assert fires(gate, old, new) is True, (
            "removing the conjunction changed NOTHING, so either Rule 2 earns "
            "nothing in the presence of Rule 1, or this arm is not measuring "
            "what it claims"
        )

    def test_removing_rule_1_changes_a_named_case_while_rule_2_stays(
        self, gate, monkeypatch, tmp_path
    ):
        """Ablate the same-slice selection. Rule 2 stays. S2 must change.

        The removal restores the per-side branch choice, which is the shipped
        behaviour before this repair.
        """
        old = unmanaged([PIN_A, PIN_B, PIN_C, PIN_D], outside=OUT_OF_REGION)
        new = managed(
            [PIN_A, PIN_B, PIN_C, PIN_D, PIN_E], outside=OUT_OF_REGION
        )
        assert fires(gate, old, new, "Write", tmp_path) is True

        def per_side(old_text, new_text):
            """Each side picks its own slice, which is the straddle."""
            from shared.claude_md_manager import extract_managed_region

            def one(text):
                got = extract_managed_region(text)
                return gate._count_pin_comments(got[0] if got else text)

            return one(new_text) > one(old_text)

        monkeypatch.setattr(gate, "_counts_show_an_add", per_side)

        # POSITIVE CONTROL: the ablation reached the decision.
        assert gate._counts_show_an_add is per_side
        assert fires(gate, old, new, "Write", tmp_path) is False, (
            "removing the same-slice rule changed NOTHING on S2, so either it "
            "earns nothing, or this fixture cannot exhibit a straddle"
        )
