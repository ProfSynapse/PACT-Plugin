"""
pact-plugin/skills/pact-handoff-harvest/test_skill_loading_harvest.py

Tests for verifying the pact-handoff-harvest skill file structure and content.
Ensures SKILL.md exists, has valid YAML frontmatter, includes all three workflow
variants, supporting sections, keyword routing, and critical protocol references.
"""

import pytest
from pathlib import Path
import yaml


SKILL_DIR = Path(__file__).parent
SKILL_FILE = SKILL_DIR / "SKILL.md"
AGENTS_DIR = SKILL_DIR.parent.parent / "agents"
SECRETARY_FILE = AGENTS_DIR / "pact-secretary.md"

ORPHAN_HEADING = "## Orphaned Handoff Recovery"

# A known sentence of the Orphaned Handoff Recovery section, used as the
# anchor of the non-vacuity guard. It must sit in that section and in no
# other.
ORPHAN_ANCHOR = "Layer 4 fallback"

# The population rule's opening phrase. It must appear ONCE: the ordering arm
# locates the rule with `find`, which returns the FIRST occurrence, so a
# second mention placed earlier would let the block itself sit anywhere.
RULE_PHRASE = "DISCARD ANY SCOPE YOU ARRIVED WITH"

# The two sweeping entry points. Each must POINT AT the population rule.
# NOT `## Standard Harvest Workflow`: see `section` on why it cannot be sliced.
SWEEPING_HEADINGS = (
    "## Incremental Harvest Workflow",
    "## Consolidation Harvest Workflow",
)

# The reference each sweeping section must carry. Deliberately NOT the pointer
# sentence: the property under test is that the section REFERS to the rule, so
# a reworded pointer must stay green and an INLINED COPY of the rule must fail.
# Deliberately NOT "Standard Harvest rule" either — "Standard Harvest Step"
# already appears in both sections, so that shorter phrase is one reword of
# existing text away from being satisfied with no pointer present.
POINTER_ANCHOR = "Standard Harvest population rule"

# Call spellings that remove a file from disk. THIS LIST IS A FLOOR AND NOT
# A PROOF OF ABSENCE: prose can authorise a removal in words no list
# anticipates. The POSITIVE assertion carries the contract. This list catches
# the machine-shaped forms an editor pastes back in.
REMOVAL_CALL_TOKENS = ("unlink", "shutil.rmtree", "os.remove", "os.rmdir", "rm -")


def section(content, heading):
    """Return the slice of `content` running from `heading` to the next `## `.

    Runs to the end of the file when that section is the last one. THE SLICE
    RULE IS THE PARAMETER OF EVERY ARM THAT USES IT, so each arm asserts the
    slice terminated correctly before it reads anything out of it.

    DO NOT SLICE `## Standard Harvest Workflow` WITH THIS. That slice
    terminates on the `## team={team_id}` file-format example inside Step 8
    and never reaches Steps 9 or 10, so an absence read out of it would be an
    absence from two thirds of a section. The Incremental and Consolidation
    sections carry no interior `## ` and slice cleanly, which is why only
    those two are sliced here.
    """
    start = content.find(heading)
    if start == -1:
        return ""
    rest = content[start + len(heading):]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


@pytest.fixture
def skill_content():
    """Load the skill file content."""
    return SKILL_FILE.read_text()


@pytest.fixture
def secretary_content():
    """Load the secretary agent definition."""
    return SECRETARY_FILE.read_text()


class TestPopulationPrecedence:
    """The dispatch-is-a-hint rule, and that it arrives before Step 1.

    A secretary that reads the rule only AFTER constructing the population has
    already mis-scoped, so presence alone is not enough: the rule must sit
    ahead of Step 1."""

    def test_rule_present(self, skill_content):
        assert "DISCARD ANY SCOPE YOU ARRIVED WITH" in skill_content
        # NOT the whole sentence. The sentence carries an EXAMPLE LIST, and a
        # list is meant to grow: pinning it verbatim turns every future
        # widening into a red that forces a same-commit test edit, which is
        # how an editor learns to update pins without reading them. This
        # substring is the AXIS the list exists to close — a dispatch can hand
        # you a scope that names no task at all — and its removal is the
        # regression. The general opener is pinned above and carries the claim.
        assert "a subset of this workflow's steps" in skill_content
        assert "never the population" in skill_content
        # Verbatim IS right here: this is the load-bearing clause, it is short,
        # and rewording it IS the regression. "anything" and not "a dispatch":
        # a rule claiming precedence over one channel leaves a second channel
        # free to contradict it, which is the defect one layer up.
        assert "outranks anything that contradicts it" in skill_content

    def test_ledger_settles_the_population(self, skill_content):
        """Step 1 constructs the population; the ledger settles it. A reader
        can run the census and still trim to a dispatch range, so Step 2
        carries its own refusal."""
        # LIMB-NEUTRAL ON PURPOSE. The earlier wording named a task set, and a
        # reminder that asserts one limb of a two-limb rule can drop the other
        # — which is how five sites came to cover only the task case. A
        # reminder asserting NO limb cannot contradict the full statement,
        # whichever limb the reader is holding.
        assert "A dispatch does not narrow this list." in skill_content

    def test_workflow_selection_is_not_scope_authority(self, secretary_content):
        """The persona sentence a secretary holds BEFORE it opens the skill
        must not read as authority over what is in scope. Limb-neutral for the
        same reason as the ledger sentence above."""
        assert "never what is in scope" in secretary_content
        assert "workflow as directed by task descriptions" not in secretary_content

    def test_rule_precedes_every_workflow_section(self, skill_content):
        """The rule must sit ahead of ALL THREE workflow sections, not just
        Step 1 of the first one.

        It used to live at the end of Standard Step 0. The Incremental and
        Consolidation sections route to Standard Step 1 and never to Step 0,
        so the only statement carrying the step-subset limb sat off the path
        of the two SWEEPING readers — the ones most likely to be handed a
        step-subset scope. Placing it in the shared preamble puts it on every
        reader's path whichever variant they run, which is what lets the later
        reminders stay short without any of them having to carry both limbs.
        """
        rule = skill_content.find(RULE_PHRASE)
        assert rule != -1
        for heading in ("## Standard Harvest Workflow",) + SWEEPING_HEADINGS:
            section_start = skill_content.find(heading)
            assert section_start != -1, f"{heading!r} is absent"
            assert rule < section_start, (
                f"The population rule sits after {heading!r}, so a reader "
                f"entering there builds a population without meeting it."
            )

    def test_address_is_distinguished_from_scope(self, skill_content):
        """A scope is discarded; an address is kept. Stated as a TEST rather
        than a list, because a list of addresses can drop a member exactly the
        way the abbreviations dropped a limb."""
        assert "AN ADDRESS SAYS WHERE TO LOOK" in skill_content
        assert "dropping it would make you read MORE" in skill_content

    def test_rule_precedes_step_1(self, skill_content):
        # THE GUARD RUNS BEFORE THE OFFSET COMPARE, AND IT IS WHAT MAKES THE
        # COMPARE MEAN ANYTHING. `find` returns the FIRST occurrence, so with
        # the phrase present twice this arm tracks the earliest MENTION rather
        # than the block. A forward pointer or a table of contents carrying
        # the phrase ahead of Step 1 then satisfies the compare while the real
        # block sits after Step 1 — the exact placement this arm forbids.
        assert skill_content.count(RULE_PHRASE) == 1, (
            f"{RULE_PHRASE!r} appears {skill_content.count(RULE_PHRASE)} "
            f"times. The compare below uses `find`, which takes the FIRST "
            f"occurrence, so a second mention placed earlier would let the "
            f"rule block itself sit anywhere. State the rule once."
        )
        rule = skill_content.find(RULE_PHRASE)
        step1 = skill_content.find("### Step 1: Task Discovery")
        assert rule != -1 and step1 != -1
        assert rule < step1, "the rule must arrive before the population is built"

    @pytest.mark.parametrize("heading", SWEEPING_HEADINGS)
    def test_sweeping_workflow_points_at_the_rule(self, skill_content, heading):
        """Both sweeping entry points must POINT AT the population rule.

        The rule lives under `## Standard Harvest Workflow`, but Incremental
        and Consolidation are reader entry points of their own and each is a
        SWEEPING pass, so a reader arriving at either builds a population
        without ever meeting the rule.

        THE ASSERTION IS SECTION-SCOPED, AND THAT IS THE WHOLE ARM. A
        file-wide `in skill_content` check is green whenever the text sits
        anywhere at all — including inside Standard, where the rule already
        lives — so it would pass on a file with neither pointer present and
        measure nothing.

        AND IT NAMES THE REFERENCE, NOT THE POINTER SENTENCE. The property
        under test is that the section REFERS to the rule rather than
        restating it: a reworded pointer must stay green, and an inlined
        second copy of the rule must fail, because a second copy is the drift
        the pointer exists to avoid.
        """
        body = section(skill_content, heading)

        # --- NON-VACUITY. A runaway slice could find the OTHER section's
        # --- pointer and pass while this section carries none.
        assert body.strip(), (
            f"The {heading!r} section is empty or absent, so this arm would "
            f"report on a section that is not there."
        )
        assert "\n## " not in body, (
            f"The {heading!r} slice contains a later heading, so it did not "
            f"terminate at the section boundary and may be reading another "
            f"section's pointer."
        )

        assert POINTER_ANCHOR in body, (
            f"The {heading!r} section does not refer to the "
            f"{POINTER_ANCHOR!r}. This section is a reader entry point and a "
            f"sweeping pass, so a reader who starts here builds a population "
            f"without meeting the rule. Add a pointer, do NOT restate the "
            f"rule here — a second copy drifts."
        )


class TestArtifactLoopShape:
    """Step 3.5 must READ inside the per-feature loop, not after it.

    THIS PINS SHAPE, NOT BEHAVIOUR, AND THE DISTINCTION IS THE POINT. The
    skill describes a shell pipeline in prose; nothing here executes it, so
    these arms cannot prove the pipeline works. They catch the exact
    regression that shipped once: the read instruction sitting AFTER the
    loop, where `$ARTIFACTS` holds only the last feature.

    Behaviour was verified ONCE, by running the pipeline against a
    two-feature journal. That was a one-time proof; this is the standing
    guard, and it watches the instruction's structure alone.
    """

    LOOP_OPEN = 'while IFS= read -r FEATURE; do'
    LOOP_CLOSE = 'done <<< "$FEATURES"'
    READ_MARKER = "READ the paths HERE"

    def test_read_instruction_is_inside_the_loop(self, skill_content):
        for token in (self.LOOP_OPEN, self.LOOP_CLOSE, self.READ_MARKER):
            assert skill_content.count(token) == 1, (
                f"{token!r} appears {skill_content.count(token)} times; the "
                f"offset comparison below needs each to be unambiguous."
            )
        opened = skill_content.find(self.LOOP_OPEN)
        read = skill_content.find(self.READ_MARKER)
        closed = skill_content.find(self.LOOP_CLOSE)
        assert opened < read < closed, (
            "The artifact READ instruction must sit INSIDE the per-feature "
            "loop. $ARTIFACTS is overwritten each iteration, so a read placed "
            "after the loop harvests the last feature only, discards every "
            "other, and reports success."
        )

    def test_merge_prohibition_is_stated(self, skill_content):
        # Load-bearing clause, so pinned verbatim: the resolved object is
        # keyed by workflow alone, and every feature runs the same phases, so
        # merging drops most paths while looking well-formed.
        assert "DO NOT MERGE THE PER-FEATURE OBJECTS INTO ONE" in skill_content
        assert "keyed by `workflow` ALONE" in skill_content


class TestSkillFileExists:
    """Test that the skill file exists."""

    def test_skill_md_exists(self):
        """SKILL.md file must exist in the skill directory."""
        assert SKILL_FILE.exists(), f"SKILL.md not found at {SKILL_FILE}"

    def test_skill_md_is_file(self):
        """SKILL.md must be a regular file, not a directory."""
        assert SKILL_FILE.is_file(), f"{SKILL_FILE} exists but is not a file"


class TestYamlFrontmatter:
    """Test that YAML frontmatter is valid and has required fields."""

    @pytest.fixture
    def frontmatter(self, skill_content):
        """Extract and parse YAML frontmatter from skill file."""
        if not skill_content.startswith("---"):
            pytest.fail("SKILL.md must start with YAML frontmatter (---)")

        end_marker = skill_content.find("---", 3)
        if end_marker == -1:
            pytest.fail("SKILL.md has unclosed YAML frontmatter")

        yaml_content = skill_content[3:end_marker].strip()
        return yaml.safe_load(yaml_content)

    def test_has_name_field(self, frontmatter):
        """Frontmatter must include 'name' field."""
        assert "name" in frontmatter, "YAML frontmatter must include 'name' field"
        assert frontmatter["name"], "'name' field must not be empty"

    def test_has_description_field(self, frontmatter):
        """Frontmatter must include 'description' field."""
        assert "description" in frontmatter, "YAML frontmatter must include 'description' field"
        assert frontmatter["description"], "'description' field must not be empty"

    def test_name_matches_directory(self, frontmatter):
        """Skill name should match the directory name."""
        expected_name = SKILL_DIR.name
        assert frontmatter["name"] == expected_name, (
            f"Skill name '{frontmatter['name']}' should match directory name '{expected_name}'"
        )


class TestWorkflowSections:
    """Test that all three workflow variants are present."""

    def test_has_standard_harvest(self, skill_content):
        """Skill must include Standard Harvest Workflow section."""
        assert "## Standard Harvest Workflow" in skill_content

    def test_has_incremental_harvest(self, skill_content):
        """Skill must include Incremental Harvest Workflow section."""
        assert "## Incremental Harvest Workflow" in skill_content

    def test_has_consolidation_harvest(self, skill_content):
        """Skill must include Consolidation Harvest Workflow section."""
        assert "## Consolidation Harvest Workflow" in skill_content

    def test_section_ordering(self, skill_content):
        """Workflows must be ordered: Standard → Incremental → Consolidation."""
        standard_pos = skill_content.index("## Standard Harvest Workflow")
        incremental_pos = skill_content.index("## Incremental Harvest Workflow")
        consolidation_pos = skill_content.index("## Consolidation Harvest Workflow")
        assert standard_pos < incremental_pos < consolidation_pos, (
            "Workflow ordering must be Standard → Incremental → Consolidation"
        )


class TestSupportingSections:
    """Test that supporting sections are present."""

    def test_has_knowledge_extraction_guide(self, skill_content):
        """Skill must include Knowledge Extraction Guide section."""
        assert "## Knowledge Extraction Guide" in skill_content

    def test_has_investigation_protocol(self, skill_content):
        """Skill must include Investigation Protocol section."""
        assert "## Investigation Protocol" in skill_content

    def test_has_ad_hoc_saves(self, skill_content):
        """Skill must include Ad-Hoc Save Requests section."""
        assert "## Ad-Hoc Save Requests" in skill_content

    def test_has_orphaned_handoff_recovery(self, skill_content):
        """Skill must include Orphaned Handoff Recovery section."""
        assert "## Orphaned Handoff Recovery" in skill_content


class TestKeywordRouting:
    """Test that keyword routing maps trigger keywords to correct workflow variants."""

    @staticmethod
    def _routing_lines(content):
        """Extract lines from the keyword routing paragraph (near top of skill)."""
        return [line for line in content.splitlines() if "→" in line]

    def test_routes_harvest_keyword(self, skill_content):
        """Routing must map 'harvest' to Standard Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"harvest"' in line and "Standard Harvest" in line for line in lines), (
            "No routing line maps \'harvest\' to Standard Harvest"
        )

    def test_routes_incremental_keyword(self, skill_content):
        """Routing must map 'incremental' to Incremental Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"incremental"' in line and "Incremental Harvest" in line for line in lines), (
            "No routing line maps \'incremental\' to Incremental Harvest"
        )

    def test_routes_consolidation_keyword(self, skill_content):
        """Routing must map 'consolidation' to Consolidation Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"consolidation"' in line and "Consolidation Harvest" in line for line in lines), (
            "No routing line maps \'consolidation\' to Consolidation Harvest"
        )

    def test_routes_process_handoffs_keyword(self, skill_content):
        """Routing must map 'process HANDOFFs' to Standard Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any("process HANDOFF" in line and "Standard Harvest" in line for line in lines), (
            "No routing line maps \'process HANDOFFs\' to Standard Harvest"
        )

    def test_routes_remediation_keyword(self, skill_content):
        """Routing must map 'remediation' to Incremental Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"remediation"' in line and "Incremental Harvest" in line for line in lines), (
            "No routing line maps \'remediation\' to Incremental Harvest"
        )


class TestSecretaryIntegration:
    """Test that the secretary agent definition loads this skill."""

    def test_secretary_frontmatter_includes_skill(self, secretary_content):
        """Secretary frontmatter skills list must include pact-handoff-harvest."""
        assert "pact-handoff-harvest" in secretary_content, (
            "pact-secretary.md must list pact-handoff-harvest in frontmatter skills"
        )


class TestCriticalProtocolReferences:
    """Test that critical protocol references are present in the skill."""

    def test_has_calibration_record_reference(self, skill_content):
        """Skill must reference CalibrationRecord for variety scoring feedback."""
        assert "CalibrationRecord" in skill_content

    def test_orphan_recovery_records_and_removes_nothing(self, skill_content):
        """The recovery step must RECORD the processed ids and remove no file.

        THIS ARM REPLACES A PIN ON THE OPPOSITE CONTRACT. It used to assert
        that the skill referenced `Path.unlink`, because step 4 told the
        agent how to remove the files it had read. Either of the two file
        classes that step reads can be the ONLY carrier of a HANDOFF, so the
        step was changed to record the ids into the Step 8 ledger and to
        remove nothing. A pin demanding the removed instruction is a pin on
        a defect.

        Deleting the assertion was the other option and it is worse. This
        class is colocated with the skill, so it is the arm a reader of the
        skill directory meets, and a member that asserts nothing reads as
        coverage while it gives none.

        THE THREE PARTS RUN IN THIS ORDER AND THE ORDER IS LOAD-BEARING.
        The non-vacuity guard runs FIRST: a negative assertion on an empty
        or mis-sliced section passes forever while it measures nothing.
        Then the positive assertion carries the contract. Then the negative
        assertion catches a machine-shaped removal pasted back in.

        WHAT THIS CANNOT CATCH: the token list is a FLOOR. An instruction
        that says erase the file in plain words passes the negative part.
        The positive part is what pins the contract itself.

        A sibling arm, `TestOrphanRecoveryCarrierGuard` in
        `tests/test_skills_structure.py`, pins three carrier-test phrases of
        the same section. This arm deliberately does NOT repeat them. It
        carries the SECTION-SCOPED ABSENCE term, which no other arm covers.
        """
        body = section(skill_content, ORPHAN_HEADING)

        # --- NON-VACUITY GUARD. Four checks, and each must pass before the
        # --- assertions below can mean anything.
        assert body.strip(), (
            f"The {ORPHAN_HEADING!r} section is empty or absent, so the "
            f"assertions below would pass while measuring nothing. Either "
            f"the section was removed from the skill, or the slice rule in "
            f"`section` no longer finds its heading."
        )
        assert len(body) < len(skill_content), (
            "The section slice is the whole file, so the scope of this arm "
            "ran away and the absence check below covers text it must not."
        )
        assert ORPHAN_ANCHOR in body, (
            f"The section slice does not contain {ORPHAN_ANCHOR!r}, so it is "
            f"not the section this arm targets. Update ORPHAN_ANCHOR only "
            f"after checking the sentence moved rather than the slice."
        )
        assert "\n## " not in body, (
            "The section slice contains a later heading, so it did not "
            "terminate at the section boundary."
        )

        # --- POSITIVE. The contract the step carries now.
        assert "Do NOT remove the files you read them from" in body, (
            "The Orphaned Handoff Recovery step must tell the agent to "
            "record the processed ids and to remove no file. Its absence "
            "means the step could have reverted to a removal, and either "
            "file class it reads can be the ONLY carrier of a recovered "
            "HANDOFF. If a deliberate rewording changed the phrase, update "
            "it here and state in the update that the step removes nothing."
        )

        # --- NEGATIVE. A floor, not a proof of absence.
        for token in REMOVAL_CALL_TOKENS:
            assert token not in body, (
                f"The Orphaned Handoff Recovery step contains {token!r}, "
                f"which removes a file. That step reads the session journal "
                f"and the task files, and either can be the only carrier of "
                f"a HANDOFF, so it must record the ids and remove nothing. "
                f"REMOVAL_CALL_TOKENS is a floor: seeing one is proof of a "
                f"regression, and seeing none is not proof of safety."
            )

    def test_has_processed_tasks_tracking(self, skill_content):
        """Skill must reference processed task tracking for dedup."""
        assert "processed_tasks" in skill_content or "session_processed_tasks" in skill_content, (
            "Skill must reference processed task tracking for incremental dedup"
        )


def _prune_bullet(content: str) -> str:
    """The one Step 3 bullet that authorises removing another team's section."""
    step = section(content, "### Step 3: Consolidate and Prune")
    assert step, "Step 3 heading not found"
    lines = [ln for ln in step.splitlines() if "`## team=` sections" in ln]
    assert len(lines) == 1, "expected exactly one prune bullet in Step 3"
    return lines[0]


class TestLedgerPruneRulings:
    """The ledger is shared by every secretary across every project, so the
    prune bullet is the one instruction that can delete another instance's
    records. Each arm pins a phrase one ruling needs; removing the phrase
    reopens the deletion it closed."""

    def test_undated_section_is_unjudgeable_not_stale(self, skill_content):
        bullet = _prune_bullet(skill_content)
        assert "unjudgeable, not stale" in bullet
        # The SAME phrase as the secretary's Working Memory guard, so one grep
        # finds both three-state sites.
        assert "a criterion that cannot be evaluated never does" in bullet

    def test_guard_phrase_is_shared_with_secretary(self, skill_content, secretary_content):
        phrase = "a criterion that cannot be evaluated never does"
        assert phrase in skill_content
        assert phrase in secretary_content

    def test_age_never_prunes_and_completion_is_verified(self, skill_content):
        bullet = _prune_bullet(skill_content)
        assert "Age never prunes" in bullet
        assert "30 days" not in bullet
        assert "VERIFIED" in bullet
        # The verification names WHERE the journal is and WHICH events count.
        assert "{config_dir}/pact-sessions/{project}/{session_id}" in bullet
        assert "read-last" in bullet
        assert "--type session_end" in bullet
        assert "--type session_paused" in bullet
        assert "session-journal.jsonl` does not exist" in bullet
        # A close that was later resumed is not a completion: the newest
        # completion event must postdate the newest session_start.
        assert "--type session_start" in bullet
        assert "later than the `ts` of the `session_start` event" in bullet
        assert "the team is live and the section stays" in bullet
        # The deviation clause that stops "paused might resume, so keep it",
        # stated against the ordering rule: speculation never keeps, an
        # observed later start does.
        assert "speculation that the session might resume never keeps a section" in bullet
        assert "only an observed `session_start` later than the completion event does" in bullet

    def test_report_precedes_removal(self, skill_content):
        bullet = _prune_bullet(skill_content)
        report = bullet.find("Before removing anything, report what you would remove")
        assert report != -1
        assert "each section header with its byte size" in bullet
        assert "byte total" in bullet
        remove = bullet.find("Then remove those sections and nothing else")
        assert remove != -1
        assert report < remove
